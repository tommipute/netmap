"""Avvisi: a ogni giro del monitor, per ogni canale attivo, un messaggio con i device che non rispondono (e le porte
giù, se il canale le segue) da almeno `delay_minutes` (una volta sola) e, se richiesto, uno con quelli tornati.
Ogni canale sceglie per quali device avvisa (`_scope`) e può cambiare il testo delle righe (modelli con segnaposto).

Invio senza librerie esterne: smtplib per l'email, urllib per webhook e Telegram. Gli errori finiscono in
`last_error` del canale (visibili nell'interfaccia) e il giro dopo si riprova.
"""
import json
import logging
import re
import smtplib
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.secrets import SecretError, decrypt
from app.models import AlertChannel, AlertState, Cable, Device, DeviceRole, Interface, Location, Site
from app.models.enums import CableStatus

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

# Testi dei messaggi nella lingua del canale (AlertChannel.language). "templates" = modelli predefiniti delle righe,
# che il canale può cambiare (AlertChannel.templates); segnaposto in PLACEHOLDERS.
TEXTS = {
    "it": {
        "test_subject": "NetMap: messaggio di prova",
        "test_text": "Se leggi questo messaggio, gli avvisi di NetMap arrivano qui.",
        "devices_down_one": "{name} non risponde",
        "devices_down_many": "{n} device non rispondono",
        "ports_down_one": "{device} {port} giù",
        "ports_down_many": "{n} porte giù",
        "devices_up_one": "{name} risponde di nuovo",
        "devices_up_many": "{n} device rispondono di nuovo",
        "ports_up_one": "{device} {port} di nuovo su",
        "ports_up_many": "{n} porte di nuovo su",
        "minutes": "{n} min",
        "hours": "{n} ore",
        "templates": {
            "down": "🔴 {device} ({ip}) non risponde da {durata} · {sede} › {posizione}",
            "up": "🟢 {device} ({ip}) risponde di nuovo (giù per {durata}) · {sede} › {posizione}",
            "port_down": "🔴 {device} {porta} giù da {durata} (verso {collegata}) · {sede} › {posizione}",
            "port_up": "🟢 {device} {porta} di nuovo su (giù per {durata}) · {sede} › {posizione}",
        },
        "sample": {"device": "sw-piano1", "ip": "10.0.1.20", "site": "Sede principale",
                   "location": "Palazzina A › Piano 1", "role": "Accesso", "port": "Gi1/0/48",
                   "remote": "core-01 Te1/1/1", "description": "Uplink verso il core", "time": "12 min"},
    },
    "en": {
        "test_subject": "NetMap: test message",
        "test_text": "If you can read this message, NetMap alerts arrive here.",
        "devices_down_one": "{name} not responding",
        "devices_down_many": "{n} devices not responding",
        "ports_down_one": "{device} {port} down",
        "ports_down_many": "{n} ports down",
        "devices_up_one": "{name} responding again",
        "devices_up_many": "{n} devices responding again",
        "ports_up_one": "{device} {port} up again",
        "ports_up_many": "{n} ports up again",
        "minutes": "{n} min",
        "hours": "{n} hours",
        "templates": {
            "down": "🔴 {device} ({ip}) not responding for {time} · {site} › {location}",
            "up": "🟢 {device} ({ip}) responding again (down for {time}) · {site} › {location}",
            "port_down": "🔴 {device} {port} down for {time} (to {remote}) · {site} › {location}",
            "port_up": "🟢 {device} {port} up again (down for {time}) · {site} › {location}",
        },
        "sample": {"device": "sw-floor1", "ip": "10.0.1.20", "site": "Main site", "location": "Building A › Floor 1",
                   "role": "Access", "port": "Gi1/0/48", "remote": "core-01 Te1/1/1",
                   "description": "Uplink to the core", "time": "12 min"},
    },
}
TEMPLATE_KEYS = ("down", "up", "port_down", "port_up")
# Segnaposto dei modelli: nome inglese e nome italiano valgono in tutte e due le lingue
PLACEHOLDERS = {"device": "device", "ip": "ip", "site": "site", "sede": "site", "location": "location",
                "posizione": "location", "role": "role", "ruolo": "role", "port": "port", "porta": "port",
                "remote": "remote", "collegata": "remote", "description": "description", "descrizione": "description",
                "time": "time", "durata": "time"}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _texts(channel: AlertChannel | None = None, language: str | None = None) -> dict:
    return TEXTS.get(language or (channel.language if channel else None) or "it", TEXTS["it"])


def _templates(texts: dict, custom: dict | None) -> dict:
    return {**texts["templates"], **{k: v for k, v in (custom or {}).items() if k in TEMPLATE_KEYS and v and v.strip()}}


def render(template: str, values: dict) -> str:
    """Riempie un modello. Le parti tra parentesi o separate da " · " e " › " che hanno solo segnaposto vuoti
    spariscono: "{device} ({ip})" senza IP diventa "sw-1", non "sw-1 ()"."""
    def filled(part: str) -> bool:
        names = _PLACEHOLDER.findall(part)
        return not names or any(n not in PLACEHOLDERS or values.get(PLACEHOLDERS[n]) for n in names)

    text = re.sub(r"\s*\([^()]*\)", lambda m: m.group(0) if filled(m.group(0)) else "", template.strip())
    for separator in (" · ", " › "):
        text = separator.join(part for part in text.split(separator) if filled(part))
    text = _PLACEHOLDER.sub(lambda m: str(values.get(PLACEHOLDERS[m.group(1)]) or "") if m.group(1) in PLACEHOLDERS
                            else m.group(0), text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def unknown_placeholders(templates: dict) -> list[str]:
    return sorted({n for t in templates.values() for n in _PLACEHOLDER.findall(t or "") if n not in PLACEHOLDERS})


Sender = Callable[[AlertChannel, str, str], None]


def send(channel: AlertChannel, subject: str, text: str) -> None:
    sender = SENDERS.get(channel.type)
    if sender is None:
        raise AlertError(f"Tipo di canale sconosciuto: {channel.type}")
    sender(channel, subject, text)


def send_test(db: Session, channel: AlertChannel, sender: Sender = send) -> str | None:
    """Messaggio di prova. Ritorna l'errore, o None se è partito."""
    try:
        texts = _texts(channel)
        sender(channel, texts["test_subject"], texts["test_text"])
        channel.last_sent_at, channel.last_error = datetime.now(timezone.utc), None
    except AlertError as exc:
        channel.last_error = str(exc)
    db.commit()
    return channel.last_error


# ---------------------------------------------------------------- valutazione
DOWN = "down"  # oper_status di una porta giù (anche lowerLayerDown, vedi OPER_STATUS in discovery/snmp.py)


def _minutes(delta, texts: dict) -> str:
    minutes = max(1, round(delta.total_seconds() / 60))
    return texts["minutes"].format(n=minutes) if minutes < 90 else texts["hours"].format(n=round(minutes / 60))


def _aware(moment: datetime | None) -> datetime | None:
    return moment.replace(tzinfo=timezone.utc) if moment and not moment.tzinfo else moment


class _Names:
    """Nomi di sedi, posizioni (percorso) e ruoli, letti una volta per giro."""

    def __init__(self, db: Session):
        self.db = db
        self.sites = dict(db.execute(select(Site.id, Site.name)).all())
        self.roles = dict(db.execute(select(DeviceRole.id, DeviceRole.name)).all())
        locations = db.execute(select(Location.id, Location.parent_id, Location.path)).all()
        self.paths = {loc.id: loc.path for loc in locations}
        self.children: dict[int, list[int]] = {}
        for loc in locations:
            if loc.parent_id:
                self.children.setdefault(loc.parent_id, []).append(loc.id)

    def with_children(self, ids: list[int]) -> set[int]:
        found, todo = set(), [i for i in ids if i in self.paths]
        while todo:
            current = todo.pop()
            if current not in found:
                found.add(current)
                todo.extend(self.children.get(current, []))
        return found

    def values(self, device: Device, time: str, iface: Interface | None = None) -> dict:
        values = {
            "device": device.name,
            "ip": device.management_ip.split("/")[0] if device.management_ip else None,
            "site": self.sites.get(device.site_id),
            "location": self.paths.get(device.location_id),
            "role": self.roles.get(device.role_id),
            "description": device.description,
            "time": time,
        }
        if iface is not None:
            values |= {"port": iface.name, "description": iface.description, "remote": self.remote(iface)}
        return values

    def remote(self, iface: Interface) -> str | None:
        cable = self.db.scalars(select(Cable).where(or_(Cable.a_interface_id == iface.id,
                                                        Cable.b_interface_id == iface.id))).first()
        if cable is None:
            return None
        other = cable.b_interface if cable.a_interface_id == iface.id else cable.a_interface
        return f"{other.device.name} {other.name}" if other else None


def _scope(names: _Names, channel: AlertChannel) -> Callable[[Device], bool]:
    """I device del canale: tutto vuoto = tutti; dove (sedi, posizioni) e ruoli insieme; più i device scelti."""
    sites, roles, devices = set(channel.site_ids or []), set(channel.role_ids or []), set(channel.device_ids or [])
    locations = names.with_children(channel.location_ids or [])
    where = bool(channel.site_ids or channel.location_ids)  # posizioni eliminate: non vale "tutti"
    filtered = where or bool(roles)

    def match(device: Device) -> bool:
        if device.id in devices or (not filtered and not devices):
            return True
        if not filtered:
            return False
        return ((not where or device.site_id in sites or device.location_id in locations)
                and (not roles or device.role_id in roles))

    return match


def _down_ports(db: Session, channel: AlertChannel, in_scope: Callable[[Device], bool]) -> list[Interface]:
    """Porte giù da segnalare: solo di device che rispondono (altrimenti basta l'avviso del device)."""
    if channel.ports not in ("cabled", "selected"):
        return []
    stmt = (select(Interface).join(Device, Interface.device_id == Device.id)
            .where(Interface.oper_status == DOWN, Interface.enabled.is_(True), Device.reachable.is_(True)))
    if channel.ports == "selected":
        return list(db.scalars(stmt.where(Interface.id.in_(channel.interface_ids or [-1]))))
    cabled = select(Cable.a_interface_id).where(Cable.status == CableStatus.CONNECTED.value).union(
        select(Cable.b_interface_id).where(Cable.status == CableStatus.CONNECTED.value))
    return [i for i in db.scalars(stmt.where(Interface.id.in_(cabled))) if in_scope(i.device)]


def _subject(texts: dict, kind: str, devices: list[Device], ports: list[Interface]) -> str:
    parts = []
    if devices:
        parts.append(texts[f"devices_{kind}_many"].format(n=len(devices)) if len(devices) > 1
                     else texts[f"devices_{kind}_one"].format(name=devices[0].name))
    if ports:
        parts.append(texts[f"ports_{kind}_many"].format(n=len(ports)) if len(ports) > 1
                     else texts[f"ports_{kind}_one"].format(device=ports[0].device.name, port=ports[0].name))
    return "NetMap: " + ", ".join(parts)


def preview(language: str, templates: dict | None, ports: bool) -> dict:
    """Come arriverebbero i messaggi, con dati di esempio (per la pagina del canale)."""
    texts = _texts(language=language)
    lines = _templates(texts, templates)
    sample = texts["sample"]
    device = {"device": sample["device"], "ip": sample["ip"], "site": sample["site"], "location": sample["location"],
              "role": sample["role"], "time": sample["time"]}
    result = {}
    for kind in ("down", "up"):
        text = [render(lines[kind], device)]
        subject = [texts[f"devices_{kind}_one"].format(name=sample["device"])]
        if ports:
            text.append(render(lines[f"port_{kind}"], sample))
            subject.append(texts[f"ports_{kind}_one"].format(device=sample["device"], port=sample["port"]))
        result[kind] = {"subject": "NetMap: " + ", ".join(subject), "text": "\n".join(text)}
    result["unknown"] = unknown_placeholders(lines)
    result["defaults"] = texts["templates"]
    return result


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
    """Manda gli avvisi dovuti. Ritorna quanti device e porte sono stati segnalati giù e tornati."""
    now = now or datetime.now(timezone.utc)
    channels = list(db.scalars(select(AlertChannel).where(AlertChannel.enabled.is_(True))))
    if not channels:
        return {"down": 0, "up": 0}
    names = _Names(db)
    down_devices = list(db.scalars(select(Device).where(Device.reachable.is_(False)).order_by(Device.name)))
    totals = {"down": 0, "up": 0}
    for channel in channels:
        texts = _texts(channel)
        lines = _templates(texts, channel.templates)
        in_scope = _scope(names, channel)
        states = list(db.scalars(select(AlertState).where(AlertState.channel_id == channel.id)))
        device_states = {s.device_id: s for s in states if s.interface_id is None}
        port_states = {s.interface_id: s for s in states if s.interface_id is not None}
        delay_s = channel.delay_minutes * 60

        def since(moment: datetime | None) -> datetime:
            return _aware(moment) or now

        def long_enough(moment: datetime | None) -> bool:
            return (now - since(moment)).total_seconds() >= delay_s

        new_down = [d for d in down_devices
                    if d.id not in device_states and in_scope(d) and long_enough(d.reachable_changed_at)]
        new_ports = sorted((i for i in _down_ports(db, channel, in_scope)
                            if i.id not in port_states and long_enough(i.oper_changed_at)),
                           key=lambda i: (i.device.name, i.name))
        if new_down or new_ports:
            text = [render(lines["down"], names.values(d, _minutes(now - since(d.reachable_changed_at), texts)))
                    for d in new_down]
            text += [render(lines["port_down"], names.values(i.device, _minutes(now - since(i.oper_changed_at), texts), i))
                     for i in new_ports]
            if _deliver(channel, _subject(texts, "down", new_down, new_ports), "\n".join(text), now, sender):
                for d in new_down:
                    db.add(AlertState(channel_id=channel.id, device_id=d.id, sent_at=now,
                                      down_since=since(d.reachable_changed_at)))
                for i in new_ports:
                    db.add(AlertState(channel_id=channel.id, device_id=i.device_id, interface_id=i.id, sent_at=now,
                                      down_since=since(i.oper_changed_at)))
                totals["down"] += len(new_down) + len(new_ports)

        back_devices = [s for s in device_states.values() if db.get(Device, s.device_id).reachable is not False]
        back_ports = [s for s in port_states.values() if db.get(Interface, s.interface_id).oper_status != DOWN]
        if back_devices or back_ports:
            delivered = True
            if channel.notify_recovery:
                def lasted(state: AlertState) -> str | None:
                    return _minutes(now - _aware(state.down_since), texts) if state.down_since else None

                devices = [db.get(Device, s.device_id) for s in back_devices]
                ports = [db.get(Interface, s.interface_id) for s in back_ports]
                text = [render(lines["up"], names.values(d, lasted(s))) for d, s in zip(devices, back_devices)]
                text += [render(lines["port_up"], names.values(i.device, lasted(s), i))
                         for i, s in zip(ports, back_ports)]
                delivered = _deliver(channel, _subject(texts, "up", devices, ports), "\n".join(text), now, sender)
            if delivered:  # se l'invio non riesce lo stato resta e il giro dopo si riprova
                for state in back_devices + back_ports:
                    db.delete(state)
                totals["up"] += len(back_devices) + len(back_ports)
    db.commit()
    return totals
