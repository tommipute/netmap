"""Applica una modifica proposta dalla scansione (approvata dall'utente o automatica).

Ogni funzione solleva ApplyError con un messaggio leggibile se la modifica non è più applicabile
(es. la porta nel frattempo è stata collegata a mano). Il chiamante la esegue dentro un SAVEPOINT.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import VLAN, Cable, Device, DeviceRole, DeviceType, DiscoveryChange, Interface, IPAddress, Manufacturer, SnmpProfile
from app.models.enums import ChangeAction, ChangeObject, DeviceStatus, Source
from app.services.rules import cable_hook, interface_hook, ip_hook, vlan_hook

SNMP = Source.SNMP.value
INTERFACE_FIELDS = ("name", "if_index", "type", "speed_mbps", "mac_address", "mtu", "enabled", "description", "oper_status")


class ApplyError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hooked(hook, db: Session, obj, data: dict, is_create: bool) -> None:
    """Le regole di coerenza dell'API valgono anche qui: un 422 diventa ApplyError."""
    try:
        hook(db, obj, data, is_create)
    except HTTPException as exc:
        raise ApplyError(exc.detail) from exc


def _get(db: Session, model, object_id: int | None, what: str):
    obj = db.get(model, object_id) if object_id is not None else None
    if obj is None:
        raise ApplyError(f"{what} non esiste più")
    return obj


def _device_type_id(db: Session, ref: dict | None) -> int | None:
    if not ref:
        return None
    if ref.get("id"):
        return _get(db, DeviceType, ref["id"], "Il modello").id
    spec = ref["create"]
    existing = db.scalars(select(DeviceType).where(DeviceType.sys_object_id == spec["sys_object_id"])).first()
    if existing:
        return existing.id
    manufacturer = db.scalars(
        select(Manufacturer).where(func.lower(Manufacturer.name) == spec["manufacturer"].lower())
    ).first()
    if manufacturer is None:
        manufacturer = Manufacturer(name=spec["manufacturer"])
        db.add(manufacturer)
        db.flush()
    dev_type = db.scalars(
        select(DeviceType).where(DeviceType.manufacturer_id == manufacturer.id, DeviceType.model == spec["model"])
    ).first()
    if dev_type is None:
        role_id = spec.get("default_role_id")
        dev_type = DeviceType(manufacturer_id=manufacturer.id, model=spec["model"],
                              default_role_id=role_id if role_id and db.get(DeviceRole, role_id) else None)
        db.add(dev_type)
    if dev_type.sys_object_id is None:
        dev_type.sys_object_id = spec["sys_object_id"]
    db.flush()
    return dev_type.id


def _new_interface(db: Session, device_id: int, values: dict) -> Interface:
    duplicate = db.scalar(select(Interface.id).where(Interface.device_id == device_id, Interface.name == values["name"]))
    if duplicate:
        raise ApplyError(f"Esiste già una porta {values['name']} su questo device")
    iface = Interface(device_id=device_id, source=SNMP, last_seen_at=_now(),
                      **{k: values.get(k) for k in INTERFACE_FIELDS if values.get(k) is not None})
    db.add(iface)
    db.flush()
    return iface


def _new_ip(db: Session, address: str, interface_id: int, is_primary: bool) -> IPAddress:
    ip = IPAddress(address=address, interface_id=interface_id, is_primary=is_primary, source=SNMP, last_seen_at=_now())
    db.add(ip)
    db.flush()
    _hooked(ip_hook, db, ip, {}, True)  # IP doppione nella VRF, un solo primario per device
    return ip


# ---------------------------------------------------------------- device
def _create_device(db: Session, data: dict, change: DiscoveryChange) -> None:
    name = data["name"]
    if db.scalar(select(Device.id).where(Device.site_id == data["site_id"], func.lower(Device.name) == name.lower())):
        raise ApplyError(f"Esiste già un device {name} in questa sede")
    type_id = _device_type_id(db, data.get("device_type"))
    device = Device(
        name=name,
        site_id=data["site_id"],
        device_type_id=type_id,
        role_id=db.scalar(select(DeviceType.default_role_id).where(DeviceType.id == type_id)) if type_id else None,
        status=DeviceStatus.ACTIVE.value,
        serial=data.get("serial"),
        sys_name=data.get("sys_name"),
        sys_descr=data.get("sys_descr"),
        snmp_profile_id=data.get("snmp_profile_id") if db.get(SnmpProfile, data.get("snmp_profile_id") or 0) else None,
        source=SNMP,
        last_seen_at=_now(),
    )
    db.add(device)
    db.flush()
    ports = {i["if_index"]: _new_interface(db, device.id, i) for i in data.get("interfaces", [])}
    for ip in data.get("ips", []):
        port = ports.get(ip["if_index"])
        if port is None:
            continue
        existing = db.scalars(
            select(IPAddress).where(IPAddress.host == ip["address"].split("/")[0], IPAddress.vrf_id.is_(None))
        ).first()
        if existing is None:
            _new_ip(db, ip["address"], port.id, ip.get("is_primary", False))
        elif existing.interface_id is None:
            # Registrato ma libero (es. in IPAM o rimasto da un device eliminato): ora è di questa porta
            existing.address, existing.interface_id = ip["address"], port.id
            existing.is_primary = ip.get("is_primary", False)
            existing.last_seen_at = _now()
            db.flush()
            _hooked(ip_hook, db, existing, {}, False)
        # assegnato a un'altra porta: lo propone la prossima scansione, che lo confronta con il database
    change.device_id = device.id


def _update_device(db: Session, data: dict, change: DiscoveryChange) -> None:
    device = _get(db, Device, change.object_id, "Il device")
    if "serial" in data:
        device.serial = data["serial"]
    if "device_type" in data:
        device.device_type_id = _device_type_id(db, data["device_type"])


# ---------------------------------------------------------------- porte
def _create_interface(db: Session, data: dict, change: DiscoveryChange) -> None:
    _get(db, Device, data["device_id"], "Il device")
    _new_interface(db, data["device_id"], data)


def _vlan_id(db: Session, site_id: int | None, vid: int) -> int:
    """VLAN della sede (o globale) con quel numero: deve esistere già."""
    vlans = db.scalars(select(VLAN).where(VLAN.vid == vid, or_(VLAN.site_id == site_id, VLAN.site_id.is_(None))))
    found = sorted(vlans, key=lambda v: v.site_id is None)  # prima quella della sede
    if not found:
        raise ApplyError(f"La VLAN {vid} non esiste ancora: approva prima la sua creazione")
    return found[0].id


def _update_interface(db: Session, data: dict, change: DiscoveryChange) -> None:
    iface = _get(db, Interface, change.object_id, "La porta")
    data = dict(data)
    if "tagged_vids" in data:  # VLAN lette dallo switch: numeri da trasformare nelle VLAN della sede
        site_id = data.pop("vlan_site_id", None)
        untagged = data.pop("untagged_vid", None)
        data["untagged_vlan_id"] = _vlan_id(db, site_id, untagged) if untagged else None
        data["tagged_vlan_ids"] = [_vlan_id(db, site_id, vid) for vid in data.pop("tagged_vids")]
    for key, value in data.items():
        if key != "tagged_vlan_ids":  # le gestisce l'hook
            setattr(iface, key, value)
    _hooked(interface_hook, db, iface, data, False)


def _stale_interface(db: Session, data: dict, change: DiscoveryChange) -> None:
    db.delete(_get(db, Interface, change.object_id, "La porta"))


# ---------------------------------------------------------------- IP
def _create_ip(db: Session, data: dict, change: DiscoveryChange) -> None:
    _get(db, Interface, data["interface_id"], "La porta")
    _new_ip(db, data["address"], data["interface_id"], data.get("is_primary", False))


def _update_ip(db: Session, data: dict, change: DiscoveryChange) -> None:
    ip = _get(db, IPAddress, change.object_id, "L'indirizzo IP")
    if "interface_id" in data:
        _get(db, Interface, data["interface_id"], "La porta")
    for key, value in data.items():
        setattr(ip, key, value)
    db.flush()
    _hooked(ip_hook, db, ip, data, False)


# ---------------------------------------------------------------- VLAN
def _create_vlan(db: Session, data: dict, change: DiscoveryChange) -> None:
    exists = db.scalar(
        select(VLAN.id).where(VLAN.vid == data["vid"], or_(VLAN.site_id == data["site_id"], VLAN.site_id.is_(None)))
    )
    if exists:
        return  # creata nel frattempo (a mano o da un'altra modifica)
    vlan = VLAN(site_id=data["site_id"], vid=data["vid"], name=data["name"][:100],
                description="Trovata dalla scansione SNMP")
    db.add(vlan)
    _hooked(vlan_hook, db, vlan, data, True)
    db.flush()


# ---------------------------------------------------------------- cavi
def _new_cable(db: Session, data: dict) -> None:
    for key in ("a_interface_id", "b_interface_id"):
        _get(db, Interface, data[key], "Una delle due porte")
    cable = Cable(a_interface_id=data["a_interface_id"], b_interface_id=data["b_interface_id"], source=SNMP, last_seen_at=_now())
    _hooked(cable_hook, db, cable, data, True)  # porte libere e cablabili
    db.add(cable)
    db.flush()


def _create_cable(db: Session, data: dict, change: DiscoveryChange) -> None:
    _new_cable(db, data)


def _update_cable(db: Session, data: dict, change: DiscoveryChange) -> None:
    for cable_id in data.get("remove_cable_ids", []):
        cable = db.get(Cable, cable_id)
        if cable is not None:
            db.delete(cable)
    db.flush()
    _new_cable(db, data)


HANDLERS = {
    (ChangeObject.DEVICE.value, ChangeAction.CREATE.value): _create_device,
    (ChangeObject.DEVICE.value, ChangeAction.UPDATE.value): _update_device,
    (ChangeObject.INTERFACE.value, ChangeAction.CREATE.value): _create_interface,
    (ChangeObject.INTERFACE.value, ChangeAction.UPDATE.value): _update_interface,
    (ChangeObject.INTERFACE.value, ChangeAction.STALE.value): _stale_interface,
    (ChangeObject.IP.value, ChangeAction.CREATE.value): _create_ip,
    (ChangeObject.IP.value, ChangeAction.UPDATE.value): _update_ip,
    (ChangeObject.CABLE.value, ChangeAction.CREATE.value): _create_cable,
    (ChangeObject.CABLE.value, ChangeAction.UPDATE.value): _update_cable,
    (ChangeObject.VLAN.value, ChangeAction.CREATE.value): _create_vlan,
}

# Ordine sicuro per approvazioni in blocco: prima i device, poi porte, IP e cavi
APPLY_ORDER = {
    ChangeObject.DEVICE.value: 0,
    ChangeObject.VLAN.value: 1,  # prima delle porte, che le usano
    ChangeObject.INTERFACE.value: 2,
    ChangeObject.IP.value: 3,
    ChangeObject.CABLE.value: 4,
}


def apply_change(db: Session, change: DiscoveryChange) -> None:
    handler = HANDLERS.get((change.object_type, change.action))
    if handler is None:
        raise ApplyError(f"Modifica non gestita: {change.object_type} {change.action}")
    # Nello storico risulta "scansione" (con l'utente che ha approvato, se c'è)
    previous = db.info.get("audit_source")
    db.info["audit_source"] = "scansione"
    try:
        handler(db, change.data or {}, change)
        db.flush()
    finally:
        db.info["audit_source"] = previous
