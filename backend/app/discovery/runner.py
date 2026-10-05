"""Esecuzione dei job di scansione: coda nel database, pianificazione, registrazione delle modifiche."""
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.secrets import SecretError, decrypt
from app.discovery import snmp
from app.discovery.apply import APPLY_ORDER, ApplyError, apply_change
from app.discovery.planner import Planner, Proposal
from app.discovery.targets import TargetError, expand_targets
from app.models import DiscoveryChange, DiscoveryJob, DiscoveryRun, SnmpProfile
from app.models.enums import ChangeStatus, RunStatus

logger = logging.getLogger(__name__)

Collector = Callable[[list[str], list[snmp.Credentials]], list[snmp.HostData]]
PENDING, APPLIED, REJECTED, FAILED = (s.value for s in ChangeStatus)


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite restituisce date senza fuso: le tratto come UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class RunError(Exception):
    pass


def _log(run: DiscoveryRun, message: str) -> None:
    stamp = datetime.now().astimezone().strftime("%H:%M:%S")  # ora locale del container (variabile TZ)
    run.log = f"{run.log or ''}{stamp} {message}\n"


def load_credentials(db: Session, profile_ids: list[int]) -> list[snmp.Credentials]:
    result = []
    for profile_id in profile_ids:
        profile = db.get(SnmpProfile, profile_id)
        if profile is None:
            continue
        try:
            result.append(snmp.Credentials(
                profile_id=profile.id,
                name=profile.name,
                version=profile.version,
                port=profile.port,
                timeout=profile.timeout,
                retries=profile.retries,
                community=decrypt(profile.community_enc) if profile.community_enc else None,
                username=profile.username,
                auth_protocol=profile.auth_protocol,
                auth_key=decrypt(profile.auth_key_enc) if profile.auth_key_enc else None,
                priv_protocol=profile.priv_protocol,
                priv_key=decrypt(profile.priv_key_enc) if profile.priv_key_enc else None,
                context=profile.context_name,
            ))
        except SecretError as exc:
            raise RunError(f"Profilo {profile.name}: {exc}") from exc
    return result


# ---------------------------------------------------------------- applicazione e registrazione
def apply_in_savepoint(db: Session, change: DiscoveryChange) -> str | None:
    """Applica una modifica; ritorna il messaggio d'errore oppure None se è andata."""
    savepoint = db.begin_nested()
    try:
        apply_change(db, change)
        savepoint.commit()
        return None
    except ApplyError as exc:
        savepoint.rollback()
        return str(exc)


def record(db: Session, job: DiscoveryJob, run: DiscoveryRun, host: str, proposals: list[Proposal]) -> None:
    keys = set()
    for p in proposals:
        keys.add(p.key)
        pending = db.scalars(select(DiscoveryChange).where(DiscoveryChange.key == p.key, DiscoveryChange.status == PENDING)).first()
        if not p.auto:
            # Già rifiutata con gli stessi dati: non la si ripropone a ogni scansione
            rejected = db.scalars(
                select(DiscoveryChange)
                .where(DiscoveryChange.key == p.key, DiscoveryChange.status == REJECTED)
                .order_by(DiscoveryChange.id.desc())
            ).first()
            if pending is None and rejected is not None and rejected.data == p.data:
                continue

        change = pending or DiscoveryChange(key=p.key, status=PENDING)
        # Lo stesso cavo visto dai due switch nella stessa scansione si conta una volta sola
        already_counted = pending is not None and pending.run_id == run.id
        change.run_id, change.job_id, change.host = run.id, job.id, host
        change.device_id, change.device_label = p.device_id, p.device_label[:255]
        change.object_type, change.action, change.object_id = p.object_type, p.action, p.object_id
        # Elenco [campo, attuale, proposto]: un dizionario in JSONB perderebbe l'ordine dei campi
        change.summary, change.data = p.summary[:500], p.data
        change.diff = [[field, before, after] for field, (before, after) in p.diff.items()]
        change.error = None
        if pending is None:
            db.add(change)

        if p.auto:
            db.flush()
            error = apply_in_savepoint(db, change)
            if error is None:
                change.status, change.auto, change.decided_at = APPLIED, True, now()
                run.changes_applied += 1
                continue
            change.error = f"Applicazione automatica non riuscita: {error}"  # resta da approvare
        if not already_counted:
            run.changes_proposed += 1

    # Modifiche in attesa che questa scansione non vede più: non servono più
    stale = select(DiscoveryChange).where(
        DiscoveryChange.job_id == job.id, DiscoveryChange.host == host, DiscoveryChange.status == PENDING
    )
    if keys:
        stale = stale.where(DiscoveryChange.key.not_in(keys))
    for old in db.scalars(stale):
        db.delete(old)


def approve(db: Session, ids: list[int]) -> dict:
    changes = list(db.scalars(select(DiscoveryChange).where(DiscoveryChange.id.in_(ids), DiscoveryChange.status == PENDING)))
    changes.sort(key=lambda c: (APPLY_ORDER.get(c.object_type, 9), c.id))
    failed = []
    for change in changes:
        error = apply_in_savepoint(db, change)
        change.decided_at = now()
        if error is None:
            change.status, change.error = APPLIED, None
        else:
            change.status, change.error = FAILED, error
            failed.append({"id": change.id, "summary": change.summary, "error": error})
    db.commit()
    return {"applied": len(changes) - len(failed), "failed": failed}


def reject(db: Session, ids: list[int]) -> dict:
    changes = list(db.scalars(select(DiscoveryChange).where(DiscoveryChange.id.in_(ids), DiscoveryChange.status == PENDING)))
    for change in changes:
        change.status, change.decided_at = REJECTED, now()
    db.commit()
    return {"rejected": len(changes)}


# ---------------------------------------------------------------- esecuzione di un job
def execute_run(db: Session, run_id: int, collector: Collector | None = None) -> DiscoveryRun:
    run = db.get(DiscoveryRun, run_id)
    job = db.get(DiscoveryJob, run.job_id)
    run.status, run.started_at = RunStatus.RUNNING.value, run.started_at or now()
    try:
        hosts = expand_targets(job.targets, settings.discovery_max_hosts)
        credentials = load_credentials(db, job.profile_ids)
        if not credentials:
            raise RunError("Il job non ha profili SNMP validi")
        run.hosts_total = len(hosts)
        _log(run, f"Scansione di {len(hosts)} indirizzi con i profili: {', '.join(c.name for c in credentials)}")
        db.commit()

        collect = collector or (lambda h, c: snmp.collect_all(h, c, settings.discovery_concurrency))
        results = collect(hosts, credentials)
        run.hosts_responded = len(results)
        _log(run, f"Hanno risposto {len(results)} host su {len(hosts)}")

        for hd in sorted(results, key=lambda r: r.host):
            savepoint = db.begin_nested()
            try:
                before = (run.changes_proposed, run.changes_applied)
                proposals = Planner(db, job, now()).plan(hd)
                record(db, job, run, hd.host, proposals)
                savepoint.commit()
                proposed, applied = run.changes_proposed - before[0], run.changes_applied - before[1]
                _log(run, f"{hd.host} {hd.sys_name or '(senza sysName)'} [{hd.profile_name}]: "
                          f"{len(hd.interfaces)} porte, {len(hd.ips)} IP, {len(hd.neighbors)} vicini "
                          f"-> {proposed} da approvare, {applied} applicate")
            except Exception as exc:  # un host con dati strani non deve fermare gli altri
                savepoint.rollback()
                logger.exception("Elaborazione di %s fallita", hd.host)
                _log(run, f"{hd.host}: errore durante l'elaborazione ({exc})")
            db.commit()

        run.status = RunStatus.DONE.value
        _log(run, f"Fine: {run.changes_proposed} modifiche da approvare, {run.changes_applied} applicate in automatico")
    except (RunError, TargetError) as exc:
        db.rollback()
        run.status = RunStatus.FAILED.value
        _log(run, f"Scansione non eseguita: {exc}")
    except Exception as exc:
        db.rollback()
        logger.exception("Scansione %s fallita", run_id)
        run.status = RunStatus.FAILED.value
        _log(run, f"Errore inatteso: {exc}")
    run.finished_at = now()
    db.commit()
    return run


# ---------------------------------------------------------------- coda e pianificazione (worker)
def active_run(db: Session, job_id: int) -> DiscoveryRun | None:
    return db.scalars(
        select(DiscoveryRun).where(
            DiscoveryRun.job_id == job_id,
            DiscoveryRun.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]),
        )
    ).first()


def enqueue(db: Session, job: DiscoveryJob) -> DiscoveryRun:
    run = DiscoveryRun(job_id=job.id, status=RunStatus.QUEUED.value, requested_at=now(), log="")
    db.add(run)
    db.commit()
    return run


def schedule_due_jobs(db: Session, current: datetime | None = None) -> int:
    """Mette in coda i job pianificati arrivati alla scadenza. Ritorna quanti ne ha accodati."""
    current = current or now()
    queued = 0
    jobs = db.scalars(select(DiscoveryJob).where(DiscoveryJob.enabled.is_(True), DiscoveryJob.interval_hours.is_not(None)))
    for job in jobs:
        if active_run(db, job.id):
            continue
        last = _aware(db.scalar(select(func.max(DiscoveryRun.requested_at)).where(DiscoveryRun.job_id == job.id)))
        if last is None or last + timedelta(hours=job.interval_hours) <= current:
            enqueue(db, job)
            queued += 1
    return queued


def claim_next_run(db: Session) -> int | None:
    """Prende la prima esecuzione in coda (SKIP LOCKED: due worker non prendono la stessa)."""
    run = db.scalars(
        select(DiscoveryRun)
        .where(DiscoveryRun.status == RunStatus.QUEUED.value)
        .order_by(DiscoveryRun.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if run is None:
        db.rollback()
        return None
    run.status, run.started_at = RunStatus.RUNNING.value, now()
    db.commit()
    return run.id


def recover_interrupted(db: Session) -> int:
    """All'avvio del worker: le esecuzioni rimaste 'in corso' sono state interrotte."""
    runs = list(db.scalars(select(DiscoveryRun).where(DiscoveryRun.status == RunStatus.RUNNING.value)))
    for run in runs:
        run.status, run.finished_at = RunStatus.FAILED.value, now()
        _log(run, "Interrotta: il worker è stato riavviato durante la scansione")
    db.commit()
    return len(runs)
