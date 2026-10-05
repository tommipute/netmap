"""Regole di coerenza dei dati, eseguite prima del salvataggio (hook dei router CRUD)."""
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import VLAN, Cable, Device, Interface, IPAddress, Location, Prefix, Rack
from app.models.enums import NON_CABLEABLE_TYPES, InterfaceMode, InterfaceType


def _fail(message: str) -> None:
    raise HTTPException(422, message)


def _same(column, value):
    """Confronto che tratta NULL come un valore (es. VRF globale)."""
    return column.is_(None) if value is None else column == value


def location_hook(db: Session, loc: Location, data: dict[str, Any], is_create: bool) -> None:
    if loc.parent_id is None:
        return
    parent = db.get(Location, loc.parent_id)
    if parent.site_id != loc.site_id:
        _fail("La posizione padre appartiene a un'altra sede")
    # Evita gerarchie circolari (A dentro B dentro A)
    current, seen = parent, set()
    while current is not None and current.id not in seen:
        if loc.id is not None and current.id == loc.id:
            _fail("Gerarchia circolare: una posizione non può stare dentro se stessa")
        seen.add(current.id)
        current = db.get(Location, current.parent_id) if current.parent_id else None


def rack_hook(db: Session, rack: Rack, data: dict[str, Any], is_create: bool) -> None:
    if rack.location_id is not None and db.get(Location, rack.location_id).site_id != rack.site_id:
        _fail("La posizione appartiene a un'altra sede")


def device_hook(db: Session, device: Device, data: dict[str, Any], is_create: bool) -> None:
    if device.location_id is not None and db.get(Location, device.location_id).site_id != device.site_id:
        _fail("La posizione appartiene a un'altra sede")
    if device.rack_id is not None and db.get(Rack, device.rack_id).site_id != device.site_id:
        _fail("Il rack appartiene a un'altra sede")


def interface_hook(db: Session, iface: Interface, data: dict[str, Any], is_create: bool) -> None:
    # VLAN tagged solo sui trunk
    if iface.mode != InterfaceMode.TRUNK.value:
        if data.get("tagged_vlan_ids"):
            _fail("Le VLAN tagged si possono assegnare solo a interfacce in modalità trunk")
        iface.tagged_vlans = []
    elif "tagged_vlan_ids" in data:
        ids = data["tagged_vlan_ids"] or []
        vlans = list(db.scalars(select(VLAN).where(VLAN.id.in_(ids)))) if ids else []
        missing = set(ids) - {v.id for v in vlans}
        if missing:
            _fail(f"VLAN non trovate: {sorted(missing)}")
        iface.tagged_vlans = vlans

    # Appartenenza a un LAG
    if iface.lag_id is not None:
        lag = db.get(Interface, iface.lag_id)
        if iface.id is not None and lag.id == iface.id:
            _fail("Un'interfaccia non può essere membro di se stessa")
        if lag.device_id != iface.device_id or lag.type != InterfaceType.LAG.value:
            _fail("lag_id deve essere un'interfaccia di tipo 'lag' dello stesso device")

    # Non si può rendere virtuale un'interfaccia che ha un cavo
    if not is_create and iface.type in NON_CABLEABLE_TYPES:
        cabled = db.scalar(
            select(Cable.id).where(or_(Cable.a_interface_id == iface.id, Cable.b_interface_id == iface.id))
        )
        if cabled:
            _fail("L'interfaccia ha un cavo collegato: non può diventare virtuale o LAG")


def cable_hook(db: Session, cable: Cable, data: dict[str, Any], is_create: bool) -> None:
    a_id, b_id = cable.a_interface_id, cable.b_interface_id
    if a_id == b_id:
        _fail("Le due estremità del cavo devono essere interfacce diverse")
    for iface_id in (a_id, b_id):
        iface = db.get(Interface, iface_id)
        if iface.type in NON_CABLEABLE_TYPES:
            _fail(f"L'interfaccia '{iface.name}' è di tipo '{iface.type}' e non può avere un cavo")
    stmt = select(Cable.id).where(
        or_(Cable.a_interface_id.in_([a_id, b_id]), Cable.b_interface_id.in_([a_id, b_id]))
    )
    if cable.id is not None:
        stmt = stmt.where(Cable.id != cable.id)
    if db.scalar(stmt):
        _fail("Una delle due interfacce ha già un cavo collegato")


def vlan_hook(db: Session, vlan: VLAN, data: dict[str, Any], is_create: bool) -> None:
    stmt = select(VLAN.id).where(VLAN.vid == vlan.vid, _same(VLAN.site_id, vlan.site_id))
    if vlan.id is not None:
        stmt = stmt.where(VLAN.id != vlan.id)
    if db.scalar(stmt):
        _fail(f"La VLAN {vlan.vid} esiste già per questa sede")


def prefix_hook(db: Session, prefix: Prefix, data: dict[str, Any], is_create: bool) -> None:
    stmt = select(Prefix.id).where(Prefix.prefix == prefix.prefix, _same(Prefix.vrf_id, prefix.vrf_id))
    if prefix.id is not None:
        stmt = stmt.where(Prefix.id != prefix.id)
    if db.scalar(stmt):
        _fail(f"Il prefisso {prefix.prefix} esiste già in questa VRF")


def ip_hook(db: Session, ip: IPAddress, data: dict[str, Any], is_create: bool) -> None:
    stmt = select(IPAddress.id).where(IPAddress.host == ip.host, _same(IPAddress.vrf_id, ip.vrf_id))
    if ip.id is not None:
        stmt = stmt.where(IPAddress.id != ip.id)
    if db.scalar(stmt):
        _fail(f"L'indirizzo {ip.host} esiste già in questa VRF")

    if ip.interface_id is None:
        ip.is_primary = False  # un IP non assegnato non può essere il primario di un device
    elif ip.is_primary:
        # Un solo IP primario per device: gli altri perdono il flag
        device_id = db.scalar(select(Interface.device_id).where(Interface.id == ip.interface_id))
        others = (
            select(IPAddress)
            .select_from(IPAddress)
            .join(Interface, IPAddress.interface_id == Interface.id)
            .where(Interface.device_id == device_id, IPAddress.is_primary.is_(True))
        )
        if ip.id is not None:
            others = others.where(IPAddress.id != ip.id)
        for other in db.scalars(others):
            other.is_primary = False


def map_hook(db: Session, network_map, data: dict[str, Any], is_create: bool) -> None:
    if network_map.location_id is not None and db.get(Location, network_map.location_id).site_id != network_map.site_id:
        _fail("La posizione appartiene a un'altra sede")
