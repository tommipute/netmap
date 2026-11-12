"""Panoramica (pagina iniziale): numeri della documentazione, stato live, porte, subnet più piene, scansioni,
attività degli ultimi giorni e, per gli amministratori, aggiornamenti e backup. Una sola richiesta, solo conteggi
e poche righe: deve restare veloce anche con migliaia di device."""

import os
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    VLAN, AuditEntry, Cable, Device, DeviceRole, DiscoveryChange, DiscoveryJob, DiscoveryRun, Endpoint, Interface,
    IPAddress, NetworkMap, Prefix, Rack, Site,
)
from app.models.enums import ChangeStatus, RunStatus
from app.services import install, updater
from app.services.ipam import prefix_utilization
from app.services.monitor import SKIPPED_STATUS, status_summary

TOP = 6
ACTIVITY_DAYS = 14
PREFIX_SCAN = 300  # oltre, le subnet più piene si cercano tra le prime 300 (le più piccole: si riempiono prima)


def _count(db: Session, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _day(value) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)[:10]


def _roles(db: Session) -> list[dict]:
    rows = db.execute(
        select(DeviceRole.id, DeviceRole.name, DeviceRole.color, func.count(Device.id))
        .join(Device, Device.role_id == DeviceRole.id)
        .group_by(DeviceRole.id, DeviceRole.name, DeviceRole.color)
        .order_by(func.count(Device.id).desc(), DeviceRole.name)
    ).all()
    roles = [{"id": r[0], "name": r[1], "color": r[2], "count": r[3]} for r in rows]
    without = db.scalar(select(func.count(Device.id)).where(Device.role_id.is_(None))) or 0
    if len(roles) > TOP:
        rest = sum(r["count"] for r in roles[TOP - 1:])
        roles = roles[:TOP - 1] + [{"id": None, "name": None, "color": None, "count": rest, "others": True}]
    if without:
        roles.append({"id": None, "name": None, "color": None, "count": without, "none": True})
    return roles


def _sites(db: Session) -> list[dict]:
    down = func.count(Device.id).filter(Device.reachable.is_(False), Device.status.notin_(SKIPPED_STATUS))
    rows = db.execute(
        select(Site.id, Site.name, func.count(Device.id), down)
        .join(Device, Device.site_id == Site.id)
        .group_by(Site.id, Site.name)
        .order_by(func.count(Device.id).desc(), Site.name)
        .limit(TOP)
    ).all()
    return [{"id": r[0], "name": r[1], "count": r[2], "down": r[3]} for r in rows]


def _down(db: Session) -> list[dict]:
    rows = db.execute(
        select(Device.id, Device.name, Device.reachable_changed_at)
        .where(Device.reachable.is_(False), Device.status.notin_(SKIPPED_STATUS))
        .order_by(Device.reachable_changed_at.desc().nulls_last(), Device.name)
        .limit(TOP)
    ).all()
    return [{"id": r[0], "name": r[1], "at": r[2]} for r in rows]


def _ports(db: Session) -> dict:
    cabled = select(Cable.a_interface_id).union(select(Cable.b_interface_id)).subquery()
    return {
        "total": _count(db, Interface),
        "cabled": db.scalar(select(func.count()).select_from(cabled)) or 0,
        "up": db.scalar(select(func.count(Interface.id)).where(Interface.oper_status == "up")) or 0,
        "down": db.scalar(
            select(func.count(Interface.id)).where(Interface.oper_status == "down", Interface.enabled.is_(True))
        ) or 0,
    }


def _prefixes(db: Session) -> dict:
    candidates = list(db.scalars(select(Prefix)).all())
    total = len(candidates)
    if total > PREFIX_SCAN:  # le più piccole prima: a parità di IP sono le più piene
        candidates = sorted(candidates, key=lambda p: -int(p.prefix.rsplit("/", 1)[-1]))[:PREFIX_SCAN]
    rows = []
    for prefix in candidates:
        use = prefix_utilization(db, prefix)
        if use["total"]:
            rows.append({"id": prefix.id, "description": prefix.description, **use})
    rows.sort(key=lambda r: (-r["percent"], -r["used"], r["prefix"]))
    return {"total": total, "partial": total > PREFIX_SCAN, "items": rows[:5]}


def _activity(db: Session) -> list[dict]:
    """Modifiche per giorno (ora del server, TZ del container) negli ultimi ACTIVITY_DAYS giorni."""
    today = datetime.now().astimezone().date()
    first = today - timedelta(days=ACTIVITY_DAYS - 1)
    day = func.date(AuditEntry.at)
    if db.get_bind().dialect.name == "postgresql" and os.environ.get("TZ"):
        day = func.date(func.timezone(os.environ["TZ"], AuditEntry.at))
    since = datetime.combine(first, datetime.min.time()).astimezone()
    rows = db.execute(select(day, func.count()).where(AuditEntry.at >= since).group_by(day)).all()
    counts = {_day(r[0]): r[1] for r in rows}
    days = [(first + timedelta(days=i)).isoformat() for i in range(ACTIVITY_DAYS)]
    return [{"day": d, "count": counts.get(d, 0)} for d in days]


def _runs(db: Session, now: datetime) -> dict:
    rows = db.execute(
        select(DiscoveryRun.id, DiscoveryRun.job_id, DiscoveryJob.name, DiscoveryRun.status, DiscoveryRun.requested_at,
               DiscoveryRun.finished_at, DiscoveryRun.hosts_responded, DiscoveryRun.changes_proposed)
        .join(DiscoveryJob, DiscoveryJob.id == DiscoveryRun.job_id)
        .order_by(DiscoveryRun.requested_at.desc(), DiscoveryRun.id.desc())
        .limit(4)
    ).all()
    failed = db.scalar(
        select(func.count(DiscoveryRun.id))
        .where(DiscoveryRun.status == RunStatus.FAILED.value, DiscoveryRun.requested_at >= now - timedelta(days=7))
    ) or 0
    return {
        "jobs": _count(db, DiscoveryJob),
        "failed_week": failed,
        "last": [
            {"id": r[0], "job_id": r[1], "job_name": r[2], "status": r[3], "at": r[5] or r[4],
             "hosts": r[6], "changes": r[7]}
            for r in rows
        ],
    }


def _endpoints(db: Session, now: datetime) -> dict:
    day_ago = now - timedelta(hours=24)
    return {
        "total": _count(db, Endpoint),
        "new_day": db.scalar(select(func.count(Endpoint.id)).where(Endpoint.first_seen_at >= day_ago)) or 0,
        "moved_day": db.scalar(select(func.count(Endpoint.id)).where(Endpoint.moved_at >= day_ago)) or 0,
    }


def _maps(db: Session) -> list[dict]:
    rows = db.execute(
        select(NetworkMap.id, NetworkMap.name, Site.name)
        .join(Site, Site.id == NetworkMap.site_id)
        .order_by(NetworkMap.updated_at.desc(), NetworkMap.name)
        .limit(TOP)
    ).all()
    return [{"id": r[0], "name": r[1], "site_name": r[2]} for r in rows]


def _system() -> dict:
    """Per gli amministratori: versione disponibile e ultimo backup, da status.json dello script di aggiornamento."""
    status = updater.read_json("status.json") or {}
    backup = status.get("backup") or {}
    return {
        "kind": install.info()["kind"],
        "update_available": bool(status.get("update_available")),
        "available": status.get("available"),
        "last_backup": backup.get("last"),
    }


def dashboard(db: Session, admin: bool) -> dict:
    now = datetime.now(timezone.utc)
    statuses = dict(db.execute(select(Device.status, func.count()).group_by(Device.status)).all())
    live = status_summary(db)
    return {
        "counts": {
            "devices": sum(statuses.values()),
            "sites": _count(db, Site),
            "racks": _count(db, Rack),
            "cables": _count(db, Cable),
            "prefixes": _count(db, Prefix),
            "ip_addresses": _count(db, IPAddress),
            "vlans": _count(db, VLAN),
            "maps": _count(db, NetworkMap),
        },
        "device_status": statuses,
        "live": {**live, "down_devices": _down(db)},
        "roles": _roles(db),
        "sites": _sites(db),
        "ports": _ports(db),
        "prefixes": _prefixes(db),
        "activity": _activity(db),
        "runs": _runs(db, now),
        "pending_changes": db.scalar(
            select(func.count(DiscoveryChange.id)).where(DiscoveryChange.status == ChangeStatus.PENDING.value)
        ) or 0,
        "endpoints": _endpoints(db, now),
        "maps": _maps(db),
        "system": _system() if admin else None,
    }

