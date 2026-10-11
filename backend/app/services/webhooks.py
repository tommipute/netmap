"""Webhook delle modifiche: il worker manda a ogni indirizzo le righe nuove dello storico (services/audit.py).

Ogni POST è un JSON {"event": "changes", "sent_at", "netmap": versione, "events": [...]}, al massimo BATCH righe;
con una chiave impostata l'intestazione X-NetMap-Signature è "sha256=" + HMAC-SHA256 del corpo. Si riparte dal
cursore (ultimo id mandato): un errore o un riavvio non perdono niente, si riprova con attesa crescente.
Gli id dello storico si assegnano all'inserimento ma diventano visibili al commit: le righe di una transazione
lunga (un import) arrivano dopo righe con id più alti. Per questo i buchi sotto il cursore (`gaps`) si
ricontrollano per GAP_HOURS ore prima di lasciarli (transazione annullata, es. la simulazione di un import).
"""
import hashlib
import hmac
import json
import logging
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.secrets import SecretError, decrypt
from app.models import AuditEntry, Webhook

logger = logging.getLogger("netmap.webhooks")
BATCH = 200
TIMEOUT = 15
POLL_SECONDS = 10
GAP_HOURS = 6
RETRY = (60, 120, 300, 600, 1800)  # attese dopo errori di fila

# Tipo dello storico -> percorso dell'API, per leggere l'oggetto com'è adesso
API_PATHS = {
    "site": "sites", "location": "locations", "rack": "racks", "manufacturer": "manufacturers",
    "device_type": "device-types", "device_role": "device-roles", "device": "devices", "interface": "interfaces",
    "cable": "cables", "vlan": "vlans", "vrf": "vrfs", "prefix": "prefixes", "ip": "ip-addresses", "map": "maps",
    "snmp_profile": "snmp-profiles", "discovery_job": "discovery-jobs", "user": "users",
    "alert_channel": "alert-channels", "stack_member": "stack-members", "backup_target": "backup-targets",
    "webhook": "webhooks",
}


class WebhookError(Exception):
    pass


def event_of(entry: AuditEntry) -> dict:
    path = API_PATHS.get(entry.object_type)
    at = entry.at if entry.at is None or entry.at.tzinfo else entry.at.replace(tzinfo=timezone.utc)
    return {
        "id": entry.id,
        "at": at.isoformat() if at else None,
        "action": entry.action,
        "object_type": entry.object_type,
        "object_id": entry.object_id,
        "object": entry.label,
        "api": f"/api/{path}/{entry.object_id}" if path and entry.action != "delete" else None,
        "user": entry.username,
        "source": entry.source,
        "changes": [{"field": field, "before": before, "after": after} for field, before, after in entry.changes or []],
        "device_ids": [d for d in (entry.device_id, entry.device_id_2) if d],
    }


def matches(hook: Webhook, entry: AuditEntry) -> bool:
    return (not hook.object_types or entry.object_type in hook.object_types) and (
        not hook.actions or entry.action in hook.actions)


def post(hook: Webhook, kind: str, events: list[dict]) -> None:
    try:
        url = decrypt(hook.url_enc) if hook.url_enc else None
        secret = decrypt(hook.secret_enc) if hook.secret_enc else None
    except SecretError as exc:
        raise WebhookError(str(exc)) from exc
    if not url:
        raise WebhookError("Manca l'indirizzo del webhook")
    body = json.dumps({"event": kind, "sent_at": datetime.now(timezone.utc).isoformat(),
                       "netmap": settings.app_version or None, "events": events}, default=str).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "NetMap", "X-NetMap-Event": kind}
    if secret:
        headers["X-NetMap-Signature"] = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    context = None
    if url.startswith("https://") and not hook.verify_tls:
        context = ssl._create_unverified_context()  # noqa: S323 - scelta esplicita dell'amministratore
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        text = exc.read().decode(errors="replace")[:200]
        raise WebhookError(f"Il servizio ha risposto {exc.code}: {text}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise WebhookError(f"Servizio non raggiungibile: {getattr(exc, 'reason', exc)}") from exc


def send_test(hook: Webhook) -> None:
    now = datetime.now(timezone.utc).isoformat()
    post(hook, "test", [{
        "id": 0, "at": now, "action": "update", "object_type": "device", "object_id": 0, "object": "sw-prova",
        "api": None, "user": "netmap", "source": "utente",
        "changes": [{"field": "Note", "before": None, "after": "Messaggio di prova di NetMap"}], "device_ids": [],
    }])


def current_cursor(db: Session) -> int:
    return db.scalar(select(func.max(AuditEntry.id))) or 0


def _without(gaps: list, found: list[int]) -> list:
    """Toglie dai buchi gli id trovati (un buco può dividersi in due)."""
    out = []
    for lo, hi, since in gaps:
        start = lo
        for i in sorted(x for x in found if lo <= x <= hi):
            if i > start:
                out.append([start, i - 1, since])
            start = i + 1
        if start <= hi:
            out.append([start, hi, since])
    return out


def deliver(db: Session, hook: Webhook) -> int:
    """Manda le righe nuove (e quelle arrivate nei buchi). Restituisce quante ne ha mandate; errore = WebhookError."""
    sent = 0
    for _ in range(20):  # al massimo 20 gruppi per giro: gli altri webhook non aspettano troppo
        gaps = [g for g in (hook.gaps or []) if g[2] > time.time() - GAP_HOURS * 3600]
        late = list(db.scalars(select(AuditEntry).where(or_(*(AuditEntry.id.between(lo, hi) for lo, hi, _ in gaps)))
                               .order_by(AuditEntry.id).limit(BATCH))) if gaps else []
        new = list(db.scalars(select(AuditEntry).where(AuditEntry.id > hook.cursor).order_by(AuditEntry.id).limit(BATCH)))
        if not late and not new and gaps == (hook.gaps or []):
            return sent
        events = [event_of(e) for e in [*late, *new] if matches(hook, e)]
        if events:
            post(hook, "changes", events)
            hook.last_sent_at = datetime.now(timezone.utc)
            sent += len(events)
        # Buchi nuovi: id saltati tra il cursore e le righe nuove
        previous = hook.cursor
        for e in new:
            if e.id > previous + 1:
                gaps.append([previous + 1, e.id - 1, time.time()])
            previous = e.id
        hook.gaps = _without(gaps, [e.id for e in late])
        hook.cursor = previous
        hook.last_error = None
        hook.last_error_at = None
        db.commit()
        if len(new) < BATCH and len(late) < BATCH:
            return sent
    return sent


def _fail(db: Session, hook: Webhook, message: str) -> None:
    db.rollback()
    hook.last_error = message[:1000]
    hook.last_error_at = datetime.now(timezone.utc)
    db.commit()


def webhook_loop(session_factory) -> None:
    """Thread del worker: ogni POLL_SECONDS manda le modifiche nuove a ogni webhook attivo."""
    failures: dict[int, int] = {}
    retry_at: dict[int, float] = {}
    while True:
        try:
            with session_factory() as db:
                for hook in db.scalars(select(Webhook).where(Webhook.enabled.is_(True))).all():
                    if retry_at.get(hook.id, 0) > time.monotonic():
                        continue
                    try:
                        if count := deliver(db, hook):
                            logger.info("Webhook %s: %s modifiche mandate", hook.name, count)
                        failures.pop(hook.id, None)
                        retry_at.pop(hook.id, None)
                    except WebhookError as exc:
                        n = failures.get(hook.id, 0)
                        failures[hook.id] = n + 1
                        retry_at[hook.id] = time.monotonic() + RETRY[min(n, len(RETRY) - 1)]
                        logger.warning("Webhook %s non riuscito: %s", hook.name, exc)
                        _fail(db, hook, str(exc))
        except (OperationalError, ProgrammingError):
            time.sleep(30)  # database non pronto o migration non ancora applicata
            continue
        except Exception:
            logger.exception("Errore inatteso nell'invio dei webhook")
        time.sleep(POLL_SECONDS)
