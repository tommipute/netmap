"""Fase 4: "dov'è collegato questo PC?".

Dopo ogni scansione si uniscono le tabelle MAC di tutti gli switch letti: per ogni MAC si sceglie la porta
di accesso, scartando gli uplink (porte con un cavo o un vicino LLDP/CDP verso un altro switch della scansione).
Se il MAC resta su più porte vince quella con meno MAC: la più vicina al device.
L'IP arriva dalle tabelle ARP di router e switch L3.
"""
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.discovery.matching import find_device, short_name
from app.discovery.snmp import HostData
from app.models import VLAN, Cable, Device, Endpoint, Interface, IPAddress, Location, Rack, Site
from app.models.enums import InterfaceType


@dataclass
class _Sighting:
    mac: str
    iface: Interface
    vlan: int | None


def _uplinks(db: Session, scanned: list[tuple[Device, HostData, dict[int, Interface]]]) -> set[int]:
    """Porte che portano verso un altro switch letto in questa scansione."""
    switch_ids = {device.id for device, hd, _ in scanned if hd.fdb}
    switch_names = {name for device, _, _ in scanned for name in (device.name.lower(), short_name(device.sys_name))}
    port_ids = {iface.id for _, _, ports in scanned for iface in ports.values()}
    uplinks: set[int] = set()

    if port_ids:
        for cable in db.scalars(
            select(Cable).where(or_(Cable.a_interface_id.in_(port_ids), Cable.b_interface_id.in_(port_ids)))
        ).unique():
            for local, remote in ((cable.a_interface, cable.b_interface), (cable.b_interface, cable.a_interface)):
                if local.id in port_ids and remote.device_id in switch_ids and remote.device_id != local.device_id:
                    uplinks.add(local.id)

    for _device, hd, ports in scanned:
        for neighbor in hd.neighbors:
            iface = ports.get(neighbor.local_if_index)
            if iface is not None and short_name(neighbor.sys_name) in switch_names:
                uplinks.add(iface.id)
        # Un port-channel è un uplink se lo è una delle sue porte
        lag_ids = {iface.lag_id for iface in ports.values() if iface.id in uplinks and iface.lag_id}
        uplinks |= lag_ids
    return uplinks


def update_endpoints(db: Session, results: list[HostData], now: datetime) -> int:
    """Aggiorna la tabella endpoints con le tabelle MAC e ARP lette. Ritorna quanti MAC ha localizzato."""
    scanned: list[tuple[Device, HostData, dict[int, Interface]]] = []
    for hd in results:
        if not hd.fdb and not hd.arp:
            continue
        device = find_device(db, serial=hd.serial, sys_name=hd.sys_name, ips=[hd.host, *(ip.address for ip in hd.ips)])
        if device is None:
            continue  # device nuovo non ancora approvato: le sue tabelle si useranno dopo l'approvazione
        ports = {
            i.if_index: i
            for i in db.scalars(select(Interface).where(Interface.device_id == device.id, Interface.if_index.is_not(None)))
        }
        scanned.append((device, hd, ports))

    arp: dict[str, str] = {}
    for _device, hd, _ports in scanned:
        for entry in hd.arp:
            arp.setdefault(entry.mac, entry.ip)

    uplinks = _uplinks(db, scanned)
    sightings: list[_Sighting] = []
    for _device, hd, ports in scanned:
        for entry in hd.fdb:
            iface = ports.get(entry.if_index)
            if iface is None or iface.id in uplinks or iface.type == InterfaceType.VIRTUAL.value:
                continue
            sightings.append(_Sighting(entry.mac, iface, entry.vlan if entry.vlan is not None else hd.port_vlans.get(entry.if_index)))

    macs_per_port: dict[int, set[str]] = defaultdict(set)
    for s in sightings:
        macs_per_port[s.iface.id].add(s.mac)

    # I MAC delle porte degli switch letti non sono endpoint da cercare: sono gli apparati stessi
    scanned_ids = [device.id for device, _, _ in scanned]
    own_macs = set(db.scalars(
        select(Interface.mac_address).where(Interface.device_id.in_(scanned_ids), Interface.mac_address.is_not(None))
    )) if scanned_ids else set()

    best: dict[str, _Sighting] = {}
    for s in sightings:
        if s.mac in own_macs:
            continue
        current = best.get(s.mac)
        rank = (len(macs_per_port[s.iface.id]), s.iface.device_id, s.iface.id)
        if current is None or rank < (len(macs_per_port[current.iface.id]), current.iface.device_id, current.iface.id):
            best[s.mac] = s

    existing = {e.mac: e for e in db.scalars(select(Endpoint).where(Endpoint.mac.in_(list(best) + list(arp))))} if (best or arp) else {}
    for mac, s in best.items():
        endpoint = existing.get(mac)
        if endpoint is None:
            endpoint = existing[mac] = Endpoint(mac=mac, first_seen_at=now)
            db.add(endpoint)
        elif endpoint.interface_id not in (None, s.iface.id):
            endpoint.previous_interface_id, endpoint.moved_at = endpoint.interface_id, now
        endpoint.interface_id, endpoint.vlan = s.iface.id, s.vlan
        endpoint.macs_on_port = len(macs_per_port[s.iface.id])
        endpoint.last_seen_at = now

    for mac, ip in arp.items():
        endpoint = existing.get(mac)
        if endpoint is not None:
            endpoint.ip, endpoint.ip_seen_at = ip, now
    db.flush()
    return len(best)


# ---------------------------------------------------------------- lettura
def _hex(text: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", text).upper()


def endpoint_rows(db: Session, endpoints: list[Endpoint]) -> list[dict]:
    """Endpoint con switch, porta, luogo e cosa si sa già di quel MAC/IP nella documentazione."""
    if not endpoints:
        return []
    device_ids = {e.interface.device_id for e in endpoints if e.interface} | {
        e.previous_interface.device_id for e in endpoints if e.previous_interface
    }
    devices = {d.id: d for d in db.scalars(select(Device).where(Device.id.in_(device_ids)))} if device_ids else {}
    sites = dict(db.execute(select(Site.id, Site.name)).all())
    locations = dict(db.execute(select(Location.id, Location.name)).all())
    racks = dict(db.execute(select(Rack.id, Rack.name)).all())
    vlan_names = {vid: name for vid, name in db.execute(select(VLAN.vid, VLAN.name)).all()}

    ips = [e.ip for e in endpoints if e.ip]
    documented_ips = {
        ip.host: ip for ip in db.scalars(select(IPAddress).where(IPAddress.host.in_(ips))).unique()
    } if ips else {}
    macs = [e.mac for e in endpoints]
    documented_ports = {
        i.mac_address: i for i in db.scalars(select(Interface).where(Interface.mac_address.in_(macs))).unique()
    }

    rows = []
    for e in endpoints:
        switch = devices.get(e.interface.device_id) if e.interface else None
        previous = devices.get(e.previous_interface.device_id) if e.previous_interface else None
        ip_doc = documented_ips.get(e.ip) if e.ip else None
        port_doc = documented_ports.get(e.mac)
        known_device_id = port_doc.device_id if port_doc else (ip_doc.device_id if ip_doc else None)
        known_as = None
        if port_doc:
            known_as = f"{port_doc.device_name} {port_doc.name}"
        elif ip_doc:
            known_as = ip_doc.dns_name or (f"{ip_doc.device_name} {ip_doc.interface_name}" if ip_doc.device_name else ip_doc.description)
        rows.append({
            "id": e.id,
            "mac": e.mac,
            "ip": e.ip,
            "vlan": e.vlan,
            "vlan_name": vlan_names.get(e.vlan),
            "device_id": switch.id if switch else None,
            "device_name": switch.name if switch else None,
            "interface_id": e.interface_id,
            "interface_name": e.interface.name if e.interface else None,
            "interface_description": e.interface.description if e.interface else None,
            "site": sites.get(switch.site_id) if switch else None,
            "location": locations.get(switch.location_id) if switch and switch.location_id else None,
            "rack": racks.get(switch.rack_id) if switch and switch.rack_id else None,
            "macs_on_port": e.macs_on_port,
            "previous_device_name": previous.name if previous else None,
            "previous_interface_name": e.previous_interface.name if e.previous_interface else None,
            "moved_at": e.moved_at,
            "first_seen_at": e.first_seen_at,
            "last_seen_at": e.last_seen_at,
            "ip_seen_at": e.ip_seen_at,
            "known_as": known_as,
            "known_device_id": known_device_id,
        })
    return rows


def endpoint_query(q: str | None = None, device_id: int | None = None, interface_id: int | None = None):
    stmt = select(Endpoint)
    if device_id is not None:
        stmt = stmt.join(Interface, Endpoint.interface_id == Interface.id).where(Interface.device_id == device_id)
    if interface_id is not None:
        stmt = stmt.where(Endpoint.interface_id == interface_id)
    term = (q or "").strip()
    if term:
        conditions = [Endpoint.ip.like(f"{term}%")]
        hex_only = _hex(term)
        if len(hex_only) >= 4 and re.fullmatch(r"[0-9A-Fa-f:.\-]+", term):
            conditions.append(func.replace(Endpoint.mac, ":", "").like(f"%{hex_only}%"))
        # Nome DNS documentato in IPAM -> IP -> endpoint
        conditions.append(Endpoint.ip.in_(select(IPAddress.host).where(IPAddress.dns_name.ilike(f"%{term}%"))))
        stmt = stmt.where(or_(*conditions))
    return stmt.order_by(Endpoint.last_seen_at.desc(), Endpoint.mac)

