"""Topologia (base per le mappe), porte di un device, mappe salvate e ricerca globale."""
import re
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.models import (
    VLAN,
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    Endpoint,
    Interface,
    IPAddress,
    Location,
    MapNode,
    NetworkMap,
    Rack,
)
from app.models.enums import NON_CABLEABLE_TYPES

DEFAULT_COLOR = "#888780"
DEFAULT_LEVEL = 2


def natural_key(text: str) -> list:
    """Ordina 'Gi1/0/2' prima di 'Gi1/0/10'."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


# ---------------------------------------------------------------- nodi e collegamenti
def _nodes(db: Session, device_ids: list[int]) -> list[dict]:
    if not device_ids:
        return []
    rows = db.execute(
        select(Device, DeviceRole, Rack.name)
        .select_from(Device)
        .outerjoin(DeviceRole, Device.role_id == DeviceRole.id)
        .outerjoin(Rack, Device.rack_id == Rack.id)
        .where(Device.id.in_(device_ids))
        .order_by(Device.name)
    ).all()
    primary_ips = dict(
        db.execute(
            select(Interface.device_id, IPAddress.address)
            .select_from(IPAddress)
            .join(Interface, IPAddress.interface_id == Interface.id)
            .where(IPAddress.is_primary.is_(True), Interface.device_id.in_(device_ids))
        ).all()
    )
    return [
        {
            "id": device.id,
            "name": device.name,
            "status": device.status,
            "site_id": device.site_id,
            "location_id": device.location_id,
            "role": role.name if role else None,
            "color": role.color if role else DEFAULT_COLOR,
            "level": role.level if role else DEFAULT_LEVEL,
            "primary_ip": primary_ips.get(device.id),
            "reachable": device.reachable,
            "last_check_at": device.last_check_at,
            "reachable_changed_at": device.reachable_changed_at,
            "rtt_ms": device.rtt_ms,
            "rack_id": device.rack_id,
            "rack_name": rack_name,
            "rack_position": device.rack_position,
        }
        for device, role, rack_name in rows
    ]


def _edges(db: Session, device_ids: list[int]) -> list[dict]:
    if not device_ids:
        return []
    a_side, b_side = aliased(Interface), aliased(Interface)
    rows = db.execute(
        select(Cable, a_side, b_side)
        .select_from(Cable)
        .join(a_side, Cable.a_interface_id == a_side.id)
        .join(b_side, Cable.b_interface_id == b_side.id)
        .where(a_side.device_id.in_(device_ids), b_side.device_id.in_(device_ids))
        .order_by(Cable.id)
    ).all()
    return [
        {
            "id": cable.id,
            "source": a.device_id,
            "target": b.device_id,
            "source_interface": a.name,
            "target_interface": b.name,
            "status": cable.status,
            "type": cable.type,
            "speed_mbps": a.speed_mbps or b.speed_mbps,
        }
        for cable, a, b in rows
    ]


def _location_subtree(db: Session, location_id: int) -> set[int]:
    children: dict[int | None, list[int]] = defaultdict(list)
    for loc_id, parent_id in db.execute(select(Location.id, Location.parent_id)).all():
        children[parent_id].append(loc_id)
    result, stack = {location_id}, [location_id]
    while stack:
        for child in children[stack.pop()]:
            if child not in result:
                result.add(child)
                stack.append(child)
    return result


def _scope_device_ids(db: Session, site_id: int | None, location_id: int | None) -> list[int]:
    stmt = select(Device.id)
    if site_id is not None:
        stmt = stmt.where(Device.site_id == site_id)
    if location_id is not None:
        stmt = stmt.where(Device.location_id.in_(_location_subtree(db, location_id)))
    return list(db.scalars(stmt))


def build_topology(db: Session, site_id: int | None = None, location_id: int | None = None) -> dict:
    ids = _scope_device_ids(db, site_id, location_id)
    return {"nodes": _nodes(db, ids), "edges": _edges(db, ids)}


# ---------------------------------------------------------------- mappe salvate
def map_view(db: Session, network_map: NetworkMap) -> dict:
    scope_ids = _scope_device_ids(db, network_map.site_id, network_map.location_id)
    saved = {n.device_id: n for n in db.scalars(select(MapNode).where(MapNode.map_id == network_map.id))}

    if network_map.auto_include:
        ids = scope_ids
    else:
        ids = list(saved.keys())

    nodes = _nodes(db, ids)
    for node in nodes:
        position = saved.get(node["id"])
        node["x"] = position.x if position else None
        node["y"] = position.y if position else None

    available = [] if network_map.auto_include else _nodes(db, [i for i in scope_ids if i not in saved])
    return {"map": network_map, "nodes": nodes, "edges": _edges(db, ids), "available": available}


def save_map_positions(db: Session, network_map: NetworkMap, positions: list) -> int:
    by_device = {p.device_id: p for p in positions}  # se un device arriva due volte vince l'ultimo
    if by_device:
        valid = set(
            db.scalars(
                select(Device.id).where(Device.id.in_(list(by_device)), Device.site_id == network_map.site_id)
            )
        )
        invalid = set(by_device) - valid
        if invalid:
            raise HTTPException(422, f"Device non appartenenti alla sede della mappa: {sorted(invalid)}")
    db.execute(delete(MapNode).where(MapNode.map_id == network_map.id))
    db.add_all(MapNode(map_id=network_map.id, device_id=d, x=p.x, y=p.y) for d, p in by_device.items())
    db.commit()
    return len(by_device)


# ---------------------------------------------------------------- porte di un device
def device_ports(db: Session, device_id: int) -> list[dict]:
    interfaces = list(
        db.scalars(
            select(Interface).where(Interface.device_id == device_id).options(selectinload(Interface.tagged_vlans))
        ).unique()
    )
    ids = [i.id for i in interfaces]
    if not ids:
        return []

    links: dict[int, tuple[Cable, Interface]] = {}
    for cable in db.scalars(
        select(Cable).where(or_(Cable.a_interface_id.in_(ids), Cable.b_interface_id.in_(ids)))
    ).unique():
        links[cable.a_interface_id] = (cable, cable.b_interface)
        links[cable.b_interface_id] = (cable, cable.a_interface)

    ips: dict[int, list[dict]] = defaultdict(list)
    for ip in db.scalars(
        select(IPAddress).where(IPAddress.interface_id.in_(ids)).order_by(IPAddress.sort_key)
    ).unique():
        ips[ip.interface_id].append({"id": ip.id, "address": ip.address, "is_primary": ip.is_primary})

    endpoint_counts = dict(db.execute(
        select(Endpoint.interface_id, func.count(Endpoint.id)).where(Endpoint.interface_id.in_(ids)).group_by(Endpoint.interface_id)
    ).all())

    untagged_ids = {i.untagged_vlan_id for i in interfaces if i.untagged_vlan_id}
    vids = dict(db.execute(select(VLAN.id, VLAN.vid).where(VLAN.id.in_(untagged_ids))).all()) if untagged_ids else {}

    result = []
    for iface in sorted(interfaces, key=lambda i: natural_key(i.name)):
        cable, remote = links.get(iface.id, (None, None))
        result.append({
            "id": iface.id,
            "name": iface.name,
            "type": iface.type,
            "enabled": iface.enabled,
            "mgmt_only": iface.mgmt_only,
            "oper_status": iface.oper_status,
            "mode": iface.mode,
            "speed_mbps": iface.speed_mbps,
            "mac_address": iface.mac_address,
            "description": iface.description,
            "lag_id": iface.lag_id,
            "untagged_vlan": vids.get(iface.untagged_vlan_id),
            "tagged_vlans": [v.vid for v in iface.tagged_vlans],
            "cableable": iface.type not in NON_CABLEABLE_TYPES,
            "cable_id": cable.id if cable else None,
            "cable_type": cable.type if cable else None,
            "cable_status": cable.status if cable else None,
            "remote_device_id": remote.device_id if remote else None,
            "remote_device": remote.device.name if remote else None,
            "remote_interface_id": remote.id if remote else None,
            "remote_interface": remote.name if remote else None,
            "ips": ips.get(iface.id, []),
            "endpoints": endpoint_counts.get(iface.id, 0),
        })
    return result


# ---------------------------------------------------------------- vicini e ricerca
def device_neighbors(db: Session, device_id: int) -> list[dict]:
    return [
        {
            "cable_id": p["cable_id"],
            "cable_status": p["cable_status"],
            "local_interface_id": p["id"],
            "local_interface": p["name"],
            "remote_device_id": p["remote_device_id"],
            "remote_device": p["remote_device"],
            "remote_interface_id": p["remote_interface_id"],
            "remote_interface": p["remote_interface"],
        }
        for p in device_ports(db, device_id)
        if p["cable_id"]
    ]


_MAC_LIKE = re.compile(r"^[0-9A-Fa-f:.\-]{4,}$")


def global_search(db: Session, q: str, limit: int = 25) -> list[dict]:
    """Cerca per nome/seriale device, MAC di interfaccia, IP o nome DNS."""
    term = q.strip()
    like = f"%{term}%"
    results: list[dict] = []

    devices = db.scalars(
        select(Device)
        .where(or_(Device.name.ilike(like), Device.serial.ilike(like), Device.asset_tag.ilike(like), Device.sys_name.ilike(like)))
        .order_by(Device.name)
        .limit(limit)
    )
    for d in devices:
        results.append({"type": "device", "id": d.id, "label": d.name, "detail": d.serial, "device_id": d.id})

    if _MAC_LIKE.match(term):
        hex_only = re.sub(r"[^0-9A-Fa-f]", "", term).upper()
        if len(hex_only) >= 4:
            interfaces = db.scalars(
                select(Interface)
                .where(func.replace(Interface.mac_address, ":", "").like(f"%{hex_only}%"))
                .limit(limit)
            ).unique()
            for iface in interfaces:
                results.append({
                    "type": "interface",
                    "id": iface.id,
                    "label": f"{iface.device_name} {iface.name}",
                    "detail": iface.mac_address,
                    "device_id": iface.device_id,
                })

    ips = db.scalars(
        select(IPAddress)
        .where(or_(IPAddress.host.like(f"{term}%"), IPAddress.dns_name.ilike(like)))
        .order_by(IPAddress.sort_key)
        .limit(limit)
    ).unique()
    for ip in ips:
        where = f"{ip.device_name} {ip.interface_name}" if ip.device_name else "non assegnato"
        results.append({"type": "ip", "id": ip.id, "label": ip.address, "detail": where, "device_id": ip.device_id})

    # Endpoint visti nelle tabelle MAC: "dov'è collegato?"
    from app.services.endpoints import endpoint_query  # import locale: endpoints importa matching

    for e in db.scalars(endpoint_query(term).limit(limit)).unique():
        where = f"{e.interface.device_name} {e.interface.name}" if e.interface else "porta non più presente"
        results.append({
            "type": "endpoint",
            "id": e.id,
            "label": f"{e.mac}{f' ({e.ip})' if e.ip else ''}",
            "detail": where,
            "device_id": e.interface.device_id if e.interface else None,
        })
    return results


# ---------------------------------------------------------------- vista frontale del rack
def rack_elevation(db: Session, rack: Rack) -> dict:
    rows = db.execute(
        select(Device, DeviceType, DeviceRole)
        .select_from(Device)
        .outerjoin(DeviceType, Device.device_type_id == DeviceType.id)
        .outerjoin(DeviceRole, Device.role_id == DeviceRole.id)
        .where(Device.rack_id == rack.id)
        .order_by(Device.rack_position.desc().nulls_last(), Device.name)
    ).all()
    placed, unplaced, occupied = [], [], defaultdict(list)
    for device, dtype, role in rows:
        item = {
            "id": device.id,
            "name": device.name,
            "position": device.rack_position,
            "u_height": max(1, dtype.u_height) if dtype and dtype.u_height else 1,
            "face_label": dtype.model if dtype else None,
            "role": role.name if role else None,
            "color": role.color if role else DEFAULT_COLOR,
            "status": device.status,
            "reachable": device.reachable,
            "conflict": False,
        }
        if device.rack_position is None:
            unplaced.append(item)
            continue
        placed.append(item)
        for unit in range(device.rack_position, device.rack_position + item["u_height"]):
            occupied[unit].append(item)
            if unit > rack.u_height:
                item["conflict"] = True
    for items in occupied.values():
        if len(items) > 1:
            for item in items:
                item["conflict"] = True
    return {
        "rack_id": rack.id,
        "name": rack.name,
        "u_height": rack.u_height,
        "used_units": len([u for u in occupied if u <= rack.u_height]),
        "devices": placed,
        "unplaced": unplaced,
    }
