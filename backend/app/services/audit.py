"""Storico delle modifiche, scritto da solo a ogni salvataggio (evento after_flush della sessione).

Così ogni strada che cambia i dati (API, modifiche in blocco, scansione, import) finisce nello storico senza
doverselo ricordare. Le righe si scrivono nella stessa transazione: se il salvataggio va indietro, anche loro.

Chi ha fatto la modifica sta in session.info: "audit_user" = (id, nome) lo mette il login (api/auth.py),
"audit_source" lo mettono worker, applicazione delle modifiche della scansione e import.
Non si registrano i campi che cambiano da soli (stato live, ultima volta visto, ifIndex...) né, quando si crea un
device, le porte e gli IP creati insieme a lui: basta la riga del device.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import event, insert, inspect
from sqlalchemy.orm import Session

from app.models import (
    VLAN,
    VRF,
    AlertChannel,
    AuditEntry,
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    DiscoveryJob,
    Interface,
    IPAddress,
    Location,
    Manufacturer,
    NetworkMap,
    Prefix,
    Rack,
    Site,
    SnmpProfile,
    StackMember,
    User,
)

TRACKED: dict[type, str] = {
    Site: "site", Location: "location", Rack: "rack", Manufacturer: "manufacturer", DeviceType: "device_type",
    DeviceRole: "device_role", Device: "device", Interface: "interface", Cable: "cable", VLAN: "vlan", VRF: "vrf",
    Prefix: "prefix", IPAddress: "ip", NetworkMap: "map", SnmpProfile: "snmp_profile", DiscoveryJob: "discovery_job",
    User: "user", AlertChannel: "alert_channel", StackMember: "stack_member",
}

# Campi che cambiano da soli o derivati: non sono modifiche di qualcuno
IGNORED = {
    "id", "created_at", "updated_at", "last_seen_at", "oper_status", "if_index", "sys_name", "sys_descr",
    "reachable", "last_check_at", "reachable_changed_at", "rtt_ms", "snmp_profile_id", "token_version",
    "last_login_at", "host", "sort_key", "source", "last_sent_at", "last_error",
}
SECRETS = {"community_enc", "auth_key_enc", "priv_key_enc", "password_hash", "secret_enc"}

LABELS = {
    "name": "Nome", "status": "Stato", "site_id": "Sede", "location_id": "Posizione", "rack_id": "Rack",
    "rack_position": "Unità", "role_id": "Ruolo", "device_type_id": "Modello", "serial": "Numero di serie",
    "asset_tag": "Asset tag", "description": "Note", "address": "Indirizzo", "interface_id": "Porta",
    "is_primary": "IP di management", "dns_name": "Nome DNS", "vrf_id": "VRF", "vlan_id": "VLAN", "mode": "Modo",
    "untagged_vlan_id": "VLAN untagged", "tagged_vlans": "VLAN tagged", "enabled": "Abilitata",
    "speed_mbps": "Velocità (Mbps)", "mac_address": "MAC", "mtu": "MTU", "type": "Tipo", "mgmt_only": "Solo management",
    "lag_id": "LAG", "a_interface_id": "Lato A", "b_interface_id": "Lato B", "label": "Etichetta", "color": "Colore",
    "length": "Lunghezza", "vid": "VID", "prefix": "Prefisso", "role": "Ruolo", "active": "Attivo",
    "full_name": "Nome e cognome", "password_hash": "Password", "custom_fields": "Campi personalizzati",
    "u_height": "Altezza (U)", "level": "Livello", "model": "Modello", "manufacturer_id": "Produttore",
    "part_number": "Codice prodotto", "sys_object_id": "sysObjectID", "auto_include": "Tutti i device",
    "targets": "Indirizzi", "profile_ids": "Profili", "interval_hours": "Ogni quante ore", "community_enc": "Community",
    "auth_key_enc": "Chiave di autenticazione", "secret_enc": "Segreto", "last_sent_at": "Ultimo invio", "priv_key_enc": "Chiave di cifratura", "username": "Utente",
    "parent_id": "Dentro a", "number": "Numero del membro", "language": "Lingua", "default_role_id": "Ruolo predefinito", "enabled_job": "Attiva",
}

# Colonne che puntano ad altri oggetti: nello storico il nome, non l'id
REFERENCES: dict[str, type] = {
    "site_id": Site, "location_id": Location, "parent_id": Location, "rack_id": Rack, "role_id": DeviceRole,
    "default_role_id": DeviceRole, "device_type_id": DeviceType, "manufacturer_id": Manufacturer, "vrf_id": VRF,
    "vlan_id": VLAN, "untagged_vlan_id": VLAN, "interface_id": Interface, "a_interface_id": Interface,
    "b_interface_id": Interface, "lag_id": Interface, "device_id": Device,
}


def label_of(session: Session, obj: Any) -> str:
    if isinstance(obj, Interface):
        device = session.get(Device, obj.device_id) if obj.device_id else None
        return f"{device.name if device else '?'} {obj.name}"
    if isinstance(obj, Cable):
        a = session.get(Interface, obj.a_interface_id)
        b = session.get(Interface, obj.b_interface_id)
        return f"{label_of(session, a) if a else '?'} ↔ {label_of(session, b) if b else '?'}"
    if isinstance(obj, VLAN):
        return f"{obj.vid} {obj.name}"
    if isinstance(obj, StackMember):
        device = session.get(Device, obj.device_id) if obj.device_id else None
        return f"{device.name if device else '?'} membro {obj.number}"
    if isinstance(obj, IPAddress):
        return obj.address
    if isinstance(obj, Prefix):
        return obj.prefix
    if isinstance(obj, DeviceType):
        return obj.model
    if isinstance(obj, User):
        return obj.username
    return str(getattr(obj, "name", None) or f"#{obj.id}")


def _devices(session: Session, obj: Any) -> tuple[int | None, int | None]:
    if isinstance(obj, Device):
        return obj.id, None
    if isinstance(obj, (Interface, StackMember)):
        return obj.device_id, None
    if isinstance(obj, IPAddress) and obj.interface_id:
        iface = session.get(Interface, obj.interface_id)
        return (iface.device_id if iface else None), None
    if isinstance(obj, Cable):
        a = session.get(Interface, obj.a_interface_id)
        b = session.get(Interface, obj.b_interface_id)
        return (a.device_id if a else None), (b.device_id if b else None)
    return None, None


def _plain(session: Session, column: str, value: Any) -> Any:
    """Valore leggibile e salvabile in JSON."""
    if value is None:
        return None
    if column in SECRETS:
        return "•••"
    if column in REFERENCES and isinstance(value, int):
        ref = session.get(REFERENCES[column], value)
        return label_of(session, ref) if ref is not None else f"#{value}"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)


def _changes(session: Session, obj: Any) -> list[list]:
    state = inspect(obj)
    out = []
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in IGNORED or key not in state.attrs:
            continue
        history = state.attrs[key].history
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else None
        if old == new:
            continue
        if key in SECRETS:
            out.append([LABELS.get(key, key), None, "cambiata"])  # i segreti non si scrivono mai
            continue
        out.append([LABELS.get(key, key), _plain(session, key, old), _plain(session, key, new)])
    if isinstance(obj, Interface):
        history = state.attrs["tagged_vlans"].history
        if history.added or history.deleted:
            before = sorted(v.vid for v in [*history.unchanged, *history.deleted])
            after = sorted(v.vid for v in [*history.unchanged, *history.added])
            if before != after:
                out.append([LABELS["tagged_vlans"], ", ".join(map(str, before)) or None, ", ".join(map(str, after)) or None])
    return out


def _who(session: Session) -> dict:
    user = session.info.get("audit_user")
    source = session.info.get("audit_source") or ("utente" if user else "sistema")
    return {"user_id": user[0] if user else None, "username": user[1] if user else None, "source": source}


@event.listens_for(Session, "after_flush")
def _record(session: Session, flush_context) -> None:
    created_devices: set = session.info.setdefault("audit_created_devices", set())
    rows = []
    with session.no_autoflush:
        for obj in session.new:
            kind = TRACKED.get(type(obj))
            if kind is None:
                continue
            if isinstance(obj, Device):
                created_devices.add(obj.id)
            # Porte e IP nati insieme al loro device (scansione, import): basta la riga del device
            device_id, _ = _devices(session, obj)
            if isinstance(obj, (Interface, IPAddress)) and device_id in created_devices:
                continue
            rows.append((obj, "create", []))
        for obj in session.dirty:
            if type(obj) not in TRACKED or not session.is_modified(obj, include_collections=True):
                continue
            changes = _changes(session, obj)
            if changes:
                rows.append((obj, "update", changes))
        for obj in session.deleted:
            if type(obj) in TRACKED:
                rows.append((obj, "delete", []))
        if not rows:
            return
        who = _who(session)
        values = []
        for obj, action, changes in rows:
            device_id, device_id_2 = _devices(session, obj)
            values.append({
                **who,
                "object_type": TRACKED[type(obj)],
                "object_id": obj.id,
                "label": label_of(session, obj)[:255],
                "action": action,
                "changes": changes,
                "device_id": device_id,
                "device_id_2": device_id_2,
            })
    session.connection().execute(insert(AuditEntry), values)


@event.listens_for(Session, "after_commit")
@event.listens_for(Session, "after_rollback")
def _reset(session: Session) -> None:
    session.info.pop("audit_created_devices", None)
