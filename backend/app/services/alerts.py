"""Avvisi: a ogni giro del monitor, per ogni canale attivo, un messaggio con i device che non rispondono da almeno
`delay_minutes` (una volta sola) e, se richiesto, uno con quelli tornati a rispondere.

Invio senza librerie esterne: smtplib per l'email, urllib per webhook e Telegram. Gli errori finiscono in
`last_error` del canale (visibili nell'interfaccia) e il giro dopo si riprova.
"""
import json
import logging
import smtplib
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secrets import SecretError, decrypt
from app.models import AlertChannel, AlertState, Device, Location, Site

logger = logging.getLogger("netmap.alerts")
TIMEOUT = 10


class AlertError(Exception):
    pass


# ---------------------------------------------------------------- invio
def _secret(channel: AlertChannel) -> str:
    if not channel.secret_enc:
        return ""
    try:
        return decrypt(channel.secret_enc)
    except SecretError as exc:
        raise AlertError(str(exc)) from exc


def _post_json(url: str, payload: dict) -> None:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:200]
        raise AlertError(f"Il servizio ha risposto {exc.code}: {body}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AlertError(f"Servizio non raggiungibile: {getattr(exc, 'reason', exc)}") from exc


def _send_email(channel: AlertChannel, subject: str, text: str) -> None:
    if not channel.email_to or not channel.smtp_host:
        raise AlertError("Mancano i destinatari o il server SMTP")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = channel.smtp_from or channel.smtp_user or "netmap@localhost"
    message["To"] = ", ".join(channel.email_to)
    message.set_content(text)
    security = channel.smtp_security or "starttls"
    port = channel.smtp_port or (465 if security == "ssl" else 587 if security == "starttls" else 25)
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(channel.smtp_host, port, timeout=TIMEOUT, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(channel.smtp_host, port, timeout=TIMEOUT)
        with server:
            if security == "starttls":
                server.starttls(context=ssl.create_default_context())
            if channel.smtp_user:
                server.login(channel.smtp_user, _secret(channel))
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise AlertError(f"Invio email non riuscito: {exc}") from exc


def _send_webhook(channel: AlertChannel, subject: str, text: str) -> None:
    url = _secret(channel)
    if not url:
        raise AlertError("Manca l'indirizzo del webhook")
    if channel.webhook_format == "teams":
        card = {
            "type": "AdaptiveCard", "version": "1.4", "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "body": [{"type": "TextBlock", "text": subject, "weight": "Bolder", "wrap": True},
                     *({"type": "TextBlock", "text": line, "wrap": True} for line in text.splitlines() if line)],
        }
        payload = {"type": "message",
                   "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}]}
    else:
        payload = {"text": f"{subject}\n{text}"}
    _post_json(url, payload)


def _send_telegram(channel: AlertChannel, subject: str, text: str) -> None:
    token = _secret(channel)
    if not token or not channel.telegram_chat_id:
        raise AlertError("Mancano il token del bot o la chat")
    _post_json(f"https://api.telegram.org/bot{token}/sendMessage",
               {"chat_id": channel.telegram_chat_id, "text": f"{subject}\n{text}"})


SENDERS = {"email": _send_email, "webhook": _send_webhook, "telegram": _send_telegram}
Sender = Callable[[AlertChannel, str, str], None]


def send(channel: AlertChannel, subject: str, text: str) -> None:
    sender = SENDERS.get(channel.type)
    if sender is None:
        raise AlertError(f"Tipo di canale sconosciuto: {channel.type}")
    sender(channel, subject, text)


def send_test(db: Session, channel: AlertChannel, sender: Sender = send) -> str | None:
    """Messaggio di prova. Ritorna l'errore, o None se è partito."""
    try:
        sender(channel, "NetMap: messaggio di prova", "Se leggi questo messaggio, gli avvisi di NetMap arrivano qui.")
        channel.last_sent_at, channel.last_error = datetime.now(timezone.utc), None
    except AlertError as exc:
        channel.last_error = str(exc)
    db.commit()
    return channel.last_error


# ---------------------------------------------------------------- valutazione
def _minutes(delta) -> str:
    minutes = max(1, round(delta.total_seconds() / 60))
    return f"{minutes} min" if minutes < 90 else f"{round(minutes / 60)} ore"


def _where(db: Session, device: Device) -> str:
    site = db.get(Site, device.site_id)
    location = db.get(Location, device.location_id) if device.location_id else None
    return ", ".join(x for x in (site.name if site else None, location.name if location else None) if x)


def _line(db: Session, device: Device, what: str) -> str:
    ip = f" ({device.management_ip.split('/')[0]})" if device.management_ip else ""
    where = _where(db, device)
    return f"{device.name}{ip} {what}" + (f" · {where}" if where else "")


def _deliver(channel: AlertChannel, subject: str, text: str, now: datetime, sender: Sender) -> bool:
    try:
        sender(channel, subject, text)
    except AlertError as exc:
        logger.warning("Avviso non inviato con %s: %s", channel.name, exc)
        channel.last_error = str(exc)
        return False
    channel.last_sent_at, channel.last_error = now, None
    return True


def process_alerts(db: Session, now: datetime | None = None, sender: Sender = send) -> dict:
    """Manda gli avvisi dovuti. Ritorna quanti device sono stati segnalati giù e tornati."""
    now = now or datetime.now(timezone.utc)
    channels = list(db.scalars(select(AlertChannel).where(AlertChannel.enabled.is_(True))))
    if not channels:
        return {"down": 0, "up": 0}
    down_devices = list(db.scalars(select(Device).where(Device.reachable.is_(False)).order_by(Device.name)))
    totals = {"down": 0, "up": 0}
    for channel in channels:
        states = {s.device_id: s for s in db.scalars(select(AlertState).where(AlertState.channel_id == channel.id))}
        delay_s = channel.delay_minutes * 60

        def since(d: Device) -> datetime:
            changed = d.reachable_changed_at or now
            return changed if changed.tzinfo else changed.replace(tzinfo=timezone.utc)

        new_down = [d for d in down_devices if d.id not in states and (now - since(d)).total_seconds() >= delay_s]
        back = [s for s in states.values() if db.get(Device, s.device_id).reachable is not False]
        if new_down:
            subject = f"NetMap: {len(new_down)} device non rispondono" if len(new_down) > 1 else f"NetMap: {new_down[0].name} non risponde"
            text = "\n".join(f"🔴 {_line(db, d, f'non risponde da {_minutes(now - since(d))}')}" for d in new_down)
            if _deliver(channel, subject, text, now, sender):
                for d in new_down:
                    db.add(AlertState(channel_id=channel.id, device_id=d.id, sent_at=now, down_since=since(d)))
                totals["down"] += len(new_down)
        if back:
            delivered = True
            if channel.notify_recovery:
                lines = []
                for state in back:
                    device = db.get(Device, state.device_id)
                    down_since = state.down_since
                    if down_since and not down_since.tzinfo:
                        down_since = down_since.replace(tzinfo=timezone.utc)
                    lasted = f" (giù per {_minutes(now - down_since)})" if down_since else ""
                    lines.append(f"🟢 {_line(db, device, 'risponde di nuovo' + lasted)}")
                first = db.get(Device, back[0].device_id)
                subject = f"NetMap: {len(back)} device rispondono di nuovo" if len(back) > 1 else f"NetMap: {first.name} risponde di nuovo"
                delivered = _deliver(channel, subject, "\n".join(lines), now, sender)
            if delivered:  # se l'invio non riesce lo stato resta e il giro dopo si riprova
                for state in back:
                    db.delete(state)
                totals["up"] += len(back)
    db.commit()
    return totals
