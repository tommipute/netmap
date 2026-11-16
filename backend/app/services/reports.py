"""Report: porte più cariche (95° percentile), errori, porte libere, PoE e disponibilità dei device.

Si calcolano a ogni richiesta dallo storico del monitor (`port_stats`, `device_stats`) e dallo stato delle porte.
"""
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Cable, Device, DeviceStat, Interface, Location, PortStat, Rack, Site
from app.services.monitor import SKIPPED_STATUS
from app.services.port_stats import RANGES, bucket

# Porte vere: niente SVI, loopback e port-channel
PHYSICAL = Interface.type.not_in(("virtual", "lag"))
SATURATED = 0.8  # uso al 95° percentile da cui una porta è satura
AVAILABILITY_RANGES = {"7d": ("1h", timedelta(days=7)), "30d": ("1h", timedelta(days=30)),
                       "1y": ("1d", timedelta(days=365))}


def percentile(values: list[float], p: float = 0.95) -> float | None:
    """Percentile "nearest rank": il valore sotto cui sta il p% dei punti (il 95° ignora i picchi del 5% del tempo)."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p * len(ordered)) - 1)]


def _devices(db: Session, site_id: int | None) -> dict[int, dict]:
    """Device con sede, posizione e rack, per le righe dei report."""
    stmt = (select(Device.id, Device.name, Device.site_id, Site.name.label("site"), Location.name.label("location"),
                   Rack.name.label("rack"))
            .join(Site, Site.id == Device.site_id)
            .outerjoin(Location, Location.id == Device.location_id)
            .outerjoin(Rack, Rack.id == Device.rack_id))
    if site_id:
        stmt = stmt.where(Device.site_id == site_id)
    return {row.id: {"device_id": row.id, "device_name": row.name, "site_id": row.site_id, "site": row.site,
                     "location": row.location, "rack": row.rack} for row in db.execute(stmt)}


def _remote_ends(db: Session, ids: list[int]) -> dict[int, tuple[str, str]]:
    """Porta -> (device, porta) all'altro capo del cavo documentato."""
    if not ids:
        return {}
    ends = {}
    for cable in db.scalars(select(Cable).where(Cable.a_interface_id.in_(ids) | Cable.b_interface_id.in_(ids))):
        for here, there in ((cable.a_interface_id, cable.b_interface_id), (cable.b_interface_id, cable.a_interface_id)):
            ends[here] = there
    names = {i.id: (i.device.name, i.name) for i in db.scalars(select(Interface).where(Interface.id.in_(set(ends.values()))))}
    return {here: names[there] for here, there in ends.items() if there in names}


def port_usage(db: Session, range_: str, site_id: int | None = None, cabled: bool = False,
               now: datetime | None = None) -> dict:
    """Traffico di ogni porta nel periodo: media, 95° percentile e picco in entrata e in uscita, uso sulla velocità.
    Il 95° percentile si fa sui punti dello storico: 5 minuti per 1 giorno, ore per 7 e 30 giorni."""
    period, span = RANGES[range_]
    now = now or datetime.now(timezone.utc)
    devices = _devices(db, site_id)
    points = defaultdict(list)
    for row in db.execute(select(PortStat.interface_id, PortStat.seconds, PortStat.in_octets, PortStat.out_octets,
                                 PortStat.in_peak_bps, PortStat.out_peak_bps)
                          .where(PortStat.period == period, PortStat.at >= bucket(now - span, period),
                                 PortStat.seconds > 0,
                                 (PortStat.in_octets.is_not(None)) | (PortStat.out_octets.is_not(None)))):
        points[row.interface_id].append(row)
    interfaces = {i.id: i for i in db.scalars(select(Interface).where(Interface.id.in_(list(points))))} if points else {}
    remote = _remote_ends(db, list(interfaces))
    items = []
    for interface_id, rows in points.items():
        iface = interfaces.get(interface_id)
        if iface is None or iface.device_id not in devices or (cabled and interface_id not in remote):
            continue
        seconds = sum(r.seconds for r in rows)
        values = {}
        for side in ("in", "out"):
            octets = [(getattr(r, f"{side}_octets"), r.seconds) for r in rows if getattr(r, f"{side}_octets") is not None]
            bps = [o * 8 / s for o, s in octets]
            peaks = [getattr(r, f"{side}_peak_bps") for r in rows if getattr(r, f"{side}_peak_bps") is not None]
            values[f"{side}_avg_bps"] = round(sum(o for o, _ in octets) * 8 / seconds) if octets else None
            values[f"{side}_p95_bps"] = round(percentile(bps)) if bps else None
            values[f"{side}_peak_bps"] = max(peaks) if peaks else None
            values[f"{side}_octets"] = sum(o for o, _ in octets) if octets else None
        if not (values["in_octets"] or values["out_octets"]):
            continue  # contatori fermi: porta senza traffico
        p95 = max(values["in_p95_bps"] or 0, values["out_p95_bps"] or 0)
        usage = round(p95 / (iface.speed_mbps * 1e6), 4) if iface.speed_mbps else None
        far = remote.get(interface_id)
        items.append({**devices[iface.device_id], "interface_id": interface_id, "interface_name": iface.name,
                      "description": iface.description, "speed_mbps": iface.speed_mbps,
                      "remote_device": far[0] if far else None, "remote_interface": far[1] if far else None,
                      **values, "usage": usage, "saturated": usage is not None and usage >= SATURATED})
    items.sort(key=lambda i: (-(i["usage"] or 0), -max(i["in_p95_bps"] or 0, i["out_p95_bps"] or 0)))
    return {"range": range_, "period": period, "saturated_at": SATURATED, "total": len(items),
            "saturated": sum(i["saturated"] for i in items), "items": items}


def port_errors(db: Session, range_: str, site_id: int | None = None, now: datetime | None = None) -> dict:
    """Porte con errori o pacchetti scartati nel periodo, dalla peggiore."""
    period, span = RANGES[range_]
    now = now or datetime.now(timezone.utc)
    devices = _devices(db, site_id)
    sums = db.execute(
        select(PortStat.interface_id, func.sum(PortStat.errors).label("errors"), func.sum(PortStat.discards).label("discards"),
               func.max(PortStat.at).label("last_at"))
        .where(PortStat.period == period, PortStat.at >= bucket(now - span, period),
               (PortStat.errors > 0) | (PortStat.discards > 0))
        .group_by(PortStat.interface_id)).all()
    interfaces = {i.id: i for i in db.scalars(select(Interface).where(Interface.id.in_([s.interface_id for s in sums])))}
    items = []
    for s in sums:
        iface = interfaces.get(s.interface_id)
        if iface is None or iface.device_id not in devices:
            continue
        items.append({**devices[iface.device_id], "interface_id": iface.id, "interface_name": iface.name,
                      "description": iface.description, "speed_mbps": iface.speed_mbps, "duplex": iface.duplex,
                      "errors": int(s.errors or 0), "discards": int(s.discards or 0),
                      "last_at": s.last_at.replace(tzinfo=s.last_at.tzinfo or timezone.utc)})
    items.sort(key=lambda i: (-i["errors"], -i["discards"]))
    return {"range": range_, "period": period, "total": len(items), "items": items}


def free_ports(db: Session, days: int = 30, site_id: int | None = None, now: datetime | None = None) -> dict:
    """Per ogni switch letto dal monitor: porte vere, su, giù e libere (giù da almeno `days` giorni)."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    devices = _devices(db, site_id)
    ports = db.scalars(select(Interface).where(PHYSICAL, Interface.mgmt_only.is_(False), Interface.oper_status.is_not(None),
                                               Interface.device_id.in_(list(devices))).order_by(Interface.id))
    by_device = defaultdict(list)
    for port in ports:
        by_device[port.device_id].append(port)
    items = []
    for device_id, device_ports in by_device.items():
        free = [p for p in device_ports if p.oper_status != "up" and p.oper_changed_at is not None
                and p.oper_changed_at.replace(tzinfo=p.oper_changed_at.tzinfo or timezone.utc) <= since]
        up = sum(p.oper_status == "up" for p in device_ports)
        items.append({**devices[device_id], "ports": len(device_ports), "up": up, "down": len(device_ports) - up,
                      "free": len(free), "free_ports": _sorted_names(p.name for p in free)})
    items.sort(key=lambda i: (i["site"].lower(), i["device_name"].lower()))
    return {"days": days, "total": len(items), "ports": sum(i["ports"] for i in items),
            "free": sum(i["free"] for i in items), "items": items}


def _sorted_names(names) -> list[str]:
    from app.services.topology import natural_key
    return sorted(names, key=natural_key)


def poe(db: Session, site_id: int | None = None) -> dict:
    """Switch PoE: watt usati sul totale, porte che alimentano qualcosa e porte in guasto."""
    devices = _devices(db, site_id)
    switches = db.scalars(select(Device).where(Device.poe_budget_w.is_not(None), Device.id.in_(list(devices))))
    counts = defaultdict(lambda: defaultdict(int))
    for device_id, status, n in db.execute(
            select(Interface.device_id, Interface.poe_status, func.count()).where(Interface.poe_status.is_not(None))
            .group_by(Interface.device_id, Interface.poe_status)):
        counts[device_id][status] = n
    items = []
    for device in switches:
        used = device.poe_used_w
        items.append({**devices[device.id], "budget_w": device.poe_budget_w, "used_w": used,
                      "usage": round(used / device.poe_budget_w, 4) if used is not None and device.poe_budget_w else None,
                      "delivering": counts[device.id]["delivering"], "searching": counts[device.id]["searching"],
                      "fault": counts[device.id]["fault"]})
    items.sort(key=lambda i: -(i["usage"] or 0))
    return {"total": len(items), "budget_w": sum(i["budget_w"] for i in items),
            "used_w": sum(i["used_w"] or 0 for i in items), "items": items}


def availability(db: Session, range_: str, site_id: int | None = None, now: datetime | None = None) -> dict:
    """Disponibilità dei device controllati dal monitor nel periodo, dalla peggiore, con il tempo di risposta medio."""
    period, span = AVAILABILITY_RANGES[range_]
    now = now or datetime.now(timezone.utc)
    devices = _devices(db, site_id)
    sums = {row.device_id: row for row in db.execute(
        select(DeviceStat.device_id, func.sum(DeviceStat.checks).label("checks"), func.sum(DeviceStat.up_checks).label("up"),
               func.sum(DeviceStat.rtt_sum_ms).label("rtt_sum"), func.sum(DeviceStat.rtt_count).label("rtt_count"),
               func.min(DeviceStat.at).label("since"))
        .where(DeviceStat.period == period, DeviceStat.at >= bucket(now - span, period))
        .group_by(DeviceStat.device_id))}
    monitored = db.execute(select(Device.id, Device.reachable, Device.reachable_changed_at)
                           .where(Device.status.not_in(SKIPPED_STATUS), Device.id.in_(list(devices)))).all()
    items = []
    for device in monitored:
        row = sums.get(device.id)
        checks = int(row.checks) if row else 0
        since = row.since.replace(tzinfo=row.since.tzinfo or timezone.utc) if row else None
        changed = device.reachable_changed_at
        items.append({**devices[device.id], "reachable": device.reachable,
                      "reachable_changed_at": changed.replace(tzinfo=changed.tzinfo or timezone.utc) if changed else None,
                      "checks": checks, "failed": checks - int(row.up) if row else 0,
                      "availability": round(int(row.up) / checks, 5) if checks else None,
                      "rtt_ms": round(row.rtt_sum / row.rtt_count, 2) if row and row.rtt_count else None,
                      "since": since})
    items.sort(key=lambda i: (i["availability"] is None, i["availability"] or 0, i["device_name"].lower()))
    return {"range": range_, "period": period, "total": len(items), "items": items}
