"""Riepilogo "cosa è cambiato" in un periodo: modifiche, device giù o tornati, endpoint nuovi o spostati, scansioni."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditEntry, Device, DiscoveryChange, DiscoveryJob, DiscoveryRun, Endpoint
from app.models.enums import ChangeStatus, RunStatus
from app.services.endpoints import endpoint_query, endpoint_rows

LIST_LIMIT = 50


def _after(value: datetime | None, since: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:  # SQLite (test) restituisce date senza fuso
        since = since.replace(tzinfo=None)
    return value >= since


def _device_row(device: Device) -> dict:
    return {"id": device.id, "name": device.name, "at": device.reachable_changed_at}


def _endpoints(db: Session, condition, order) -> dict:
    stmt = endpoint_query().where(condition)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(db.scalars(stmt.order_by(None).order_by(order.desc()).limit(LIST_LIMIT)).unique())
    return {"total": total, "items": endpoint_rows(db, items)}


def whats_changed(db: Session, since: datetime) -> dict:
    # Modifiche: quante, da chi (utente, scansione...) e device nati o eliminati
    counts = db.execute(
        select(AuditEntry.source, AuditEntry.action, func.count())
        .where(AuditEntry.at >= since)
        .group_by(AuditEntry.source, AuditEntry.action)
    ).all()
    by_source: dict[str, int] = {}
    by_action = {"create": 0, "update": 0, "delete": 0}
    for source, action, n in counts:
        by_source[source] = by_source.get(source, 0) + n
        by_action[action] = by_action.get(action, 0) + n
    devices = db.execute(
        select(AuditEntry.action, AuditEntry.object_id, AuditEntry.label, AuditEntry.at)
        .where(AuditEntry.at >= since, AuditEntry.object_type == "device", AuditEntry.action.in_(("create", "delete")))
        .order_by(AuditEntry.at.desc(), AuditEntry.id.desc())
        .limit(LIST_LIMIT * 2)
    ).all()
    still_there = set(db.scalars(select(Device.id).where(Device.id.in_([d.object_id for d in devices]))))

    # Stato live: giù adesso (con da quando) e tornati a rispondere nel periodo
    down = db.scalars(
        select(Device).where(Device.reachable.is_(False)).order_by(Device.reachable_changed_at.desc(), Device.name)
    ).all()
    back = db.scalars(
        select(Device)
        .where(Device.reachable.is_(True), Device.reachable_changed_at >= since)
        .order_by(Device.reachable_changed_at.desc())
        .limit(LIST_LIMIT)
    ).all()

    runs = db.execute(
        select(DiscoveryRun, DiscoveryJob.name)
        .join(DiscoveryJob, DiscoveryRun.job_id == DiscoveryJob.id)
        .where(DiscoveryRun.requested_at >= since)
        .order_by(DiscoveryRun.requested_at.desc())
    ).all()
    pending = db.scalar(select(func.count(DiscoveryChange.id)).where(DiscoveryChange.status == ChangeStatus.PENDING.value))

    return {
        "since": since,
        "changes": {"total": sum(by_action.values()), "by_source": by_source, "by_action": by_action},
        "devices_created": [
            {"id": d.object_id, "name": d.label, "at": d.at, "exists": d.object_id in still_there}
            for d in devices if d.action == "create"
        ][:LIST_LIMIT],
        "devices_deleted": [{"id": d.object_id, "name": d.label, "at": d.at} for d in devices if d.action == "delete"][:LIST_LIMIT],
        "devices_down": [{**_device_row(d), "new": _after(d.reachable_changed_at, since)} for d in down],
        "devices_back": [_device_row(d) for d in back],
        "endpoints_new": _endpoints(db, Endpoint.first_seen_at >= since, Endpoint.first_seen_at),
        "endpoints_moved": _endpoints(db, Endpoint.moved_at >= since, Endpoint.moved_at),
        "runs": {
            "total": len(runs),
            "failed": [
                {"id": run.id, "job_id": run.job_id, "job_name": name, "at": run.requested_at}
                for run, name in runs if run.status == RunStatus.FAILED.value
            ],
            "changes_proposed": sum(run.changes_proposed for run, _ in runs),
            "changes_applied": sum(run.changes_applied for run, _ in runs),
        },
        "pending_changes": pending or 0,
    }
