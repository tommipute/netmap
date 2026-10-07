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
    MapCableRoute,
    MapNode,
    NetworkMap,
    Rack,
    StackMember,
)
from app.models.dcim import interface_tagged_vlans
from app.models.enums import NON_CABLEABLE_TYPES

DEFAULT_COLOR = "#888780"
DEFAULT_LEVEL = 2


def natural_key(text: str) -> list:
    """Ordina 'Gi1/0/2' prima di 'Gi1/0/10'."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


# ---------------------------------------------------------------- nodi e collegamenti
def _port_vlans(db: Session, device_ids: list[int]) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """VLAN (untagged e tagged) di ogni porta e di ogni device: {interface_id: {vlan_id}}, {device_id: {vlan_id}}."""
    by_port: dict[int, set[int]] = defaultdict(set)
    by_device: dict[int, set[int]] = defaultdict(set)
    untagged = select(Interface.id, Interface.device_id, Interface.untagged_vlan_id).where(
        Interface.device_id.in_(device_ids), Interface.untagged_vlan_id.is_not(None)
    )
    tagged = (
        select(Interface.id, Interface.device_id, interface_tagged_vlans.c.vlan_id)
        .join(interface_tagged_vlans, interface_tagged_vlans.c.interface_id == Interface.id)
        .where(Interface.device_id.in_(device_ids))
    )
    for stmt in (untagged, tagged):
        for interface_id, device_id, vlan_id in db.execute(stmt).all():
            by_port[interface_id].add(vlan_id)
            by_device[device_id].add(vlan_id)
    return by_port, by_device


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
    _, device_vlans = _port_vlans(db, device_ids)
    stack_sizes = dict(db.execute(
        select(StackMember.device_id, func.count()).where(StackMember.device_id.in_(device_ids)).group_by(StackMember.device_id)
    ).all())
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
            "vlan_ids": sorted(device_vlans.get(device.id, ())),
            "stack_size": stack_sizes.get(device.id, 0),
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
    port_vlans, _ = _port_vlans(db, device_ids)

    def cable_vlans(a: Interface, b: Interface) -> list[int]:
        # Documentate su tutti e due i lati: quelle in comune; su un lato solo (es. server senza VLAN): quelle
        va, vb = port_vlans.get(a.id, set()), port_vlans.get(b.id, set())
        return sorted(va & vb if va and vb else va | vb)

    return [
        {
            "id": cable.id,
            "source": a.device_id,
            "target": b.device_id,
            "source_interface": a.name,
            "target_interface": b.name,
            "source_interface_id": a.id,
            "target_interface_id": b.id,
            "vlan_ids": cable_vlans(a, b),
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
    vlan_ids = {v for node in nodes for v in node["vlan_ids"]}
    vlans = [
        {"id": v.id, "vid": v.vid, "name": v.name}
        for v in db.scalars(select(VLAN).where(VLAN.id.in_(vlan_ids)).order_by(VLAN.vid, VLAN.name))
    ] if vlan_ids else []
    edges = _edges(db, ids)
    cable_ids = {e["id"] for e in edges}
    routes = [
        {"cable_id": r.cable_id, "points": r.points, "a_end": (r.ends or {}).get("a"), "b_end": (r.ends or {}).get("b")}
        for r in db.scalars(select(MapCableRoute).where(MapCableRoute.map_id == network_map.id))
        if r.cable_id in cable_ids
    ]
    return {"map": network_map, "nodes": nodes, "edges": edges, "available": available, "vlans": vlans, "routes": routes}


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


def save_map_routes(db: Session, network_map: NetworkMap, routes: list) -> int:
    """Sostituisce i percorsi sistemati a mano; un cavo senza spigoli né estremità fissate torna automatico."""
    by_cable = {r.cable_id: r for r in routes if r.points or r.a_end or r.b_end}
    if by_cable:
        a_side, b_side = aliased(Interface), aliased(Interface)
        valid = set(
            db.scalars(
                select(Cable.id)
                .join(a_side, Cable.a_interface_id == a_side.id)
                .join(b_side, Cable.b_interface_id == b_side.id)
                .join(Device, a_side.device_id == Device.id)
                .where(Cable.id.in_(list(by_cable)), Device.site_id == network_map.site_id)
            )
        )
        invalid = set(by_cable) - valid
        if invalid:
            raise HTTPException(422, f"Cavi inesistenti o di un'altra sede: {sorted(invalid)}")
    db.execute(delete(MapCableRoute).where(MapCableRoute.map_id == network_map.id))
    db.add_all(
        MapCableRoute(
            map_id=network_map.id,
            cable_id=c,
            points=[{"x": round(p.x, 1), "y": round(p.y, 1)} for p in r.points],
            ends={k: v.model_dump() for k, v in (("a", r.a_end), ("b", r.b_end)) if v} or None,
        )
        for c, r in by_cable.items()
    )
    db.commit()
    return len(by_cable)


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

    # Endpoint visti su ogni porta: il numero e i primi tre, da mostrare nella tabella delle porte
    endpoints: dict[int, list[Endpoint]] = defaultdict(list)
    for e in db.scalars(
        select(Endpoint).where(Endpoint.interface_id.in_(ids)).order_by(Endpoint.ip.is_(None), Endpoint.ip, Endpoint.mac)
    ).unique():
        endpoints[e.interface_id].append(e)

    untagged_ids = {i.untagged_vlan_id for i in interfaces if i.untagged_vlan_id}
    untagged = {v.id: v for v in db.scalars(select(VLAN).where(VLAN.id.in_(untagged_ids)))} if untagged_ids else {}

    result = []
    for iface in sorted(interfaces, key=lambda i: natural_key(i.name)):
        cable, remote = links.get(iface.id, (None, None))
        native = untagged.get(iface.untagged_vlan_id)
        vlan_names = {v.vid: v.name for v in [*iface.tagged_vlans, *([native] if native else [])]}
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
            "untagged_vlan": native.vid if native else None,
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
            "vlan_names": vlan_names,
            "endpoints": len(endpoints.get(iface.id, [])),
            "endpoint_preview": [
                {"mac": e.mac, "ip": e.ip, "vlan": e.vlan} for e in endpoints.get(iface.id, [])[:3]
            ],
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
    # Seriale di uno switch di uno stack: porta al device dello stack
    for m in db.scalars(select(StackMember).where(StackMember.serial.ilike(like)).limit(limit)):
        results.append({"type": "device", "id": m.device_id, "label": m.device_name or "?",
                        "detail": f"membro {m.number} dello stack, {m.serial}", "device_id": m.device_id})

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
                    "interface_id": iface.id,
                })

    ips = db.scalars(
        select(IPAddress)
        .where(or_(IPAddress.host.like(f"{term}%"), IPAddress.dns_name.ilike(like)))
        .order_by(IPAddress.sort_key)
        .limit(limit)
    ).unique()
    for ip in ips:
        where = f"{ip.device_name} {ip.interface_name}" if ip.device_name else "non assegnato"
        results.append({
            "type": "ip", "id": ip.id, "label": ip.address, "detail": where, "device_id": ip.device_id,
            "interface_id": ip.interface_id,
        })

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
            "interface_id": e.interface_id,
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
    members = defaultdict(list)
    for m in db.scalars(
        select(StackMember).where(StackMember.device_id.in_([d.id for d, _t, _r in rows])).order_by(StackMember.number)
    ):
        members[m.device_id].append(m)
    placed, unplaced, occupied = [], [], defaultdict(list)

    def place(item: dict) -> None:
        if item["position"] is None:
            unplaced.append(item)
            return
        placed.append(item)
        for unit in range(item["position"], item["position"] + item["u_height"]):
            occupied[unit].append(item)
            if unit > rack.u_height:
                item["conflict"] = True

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
        stack = members.get(device.id, [])
        if not any(m.rack_position is not None for m in stack):
            place(item)
            continue
        # Stack con le unità dei membri: ogni switch al suo posto
        for m in stack:
            place({**item, "position": m.rack_position, "member": m.number, "member_id": m.id,
                   "face_label": m.model or item["face_label"]})
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
