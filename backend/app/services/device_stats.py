"""Disponibilità dei device: a ogni controllo del monitor (ping e SNMP, di solito ogni minuto) si somma un controllo,
riuscito o no, e il tempo di risposta alla riga dell'ora e a quella del giorno (ora locale del server).
Le ore restano 30 giorni, i giorni un anno. Disponibilità = controlli riusciti / controlli."""
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import DeviceStat
from app.services.port_stats import bucket

KEEP = {"1h": timedelta(days=30), "1d": timedelta(days=366)}


def record(db: Session, results: list[tuple[int, bool, float | None]], now: datetime) -> None:
    """`results` = (device_id, raggiungibile, tempo di risposta in ms) dei device controllati adesso."""
    if not results:
        return
    ids = [device_id for device_id, _, _ in results]
    for period in KEEP:
        at = bucket(now, period)
        rows = {r.device_id: r for r in db.scalars(
            select(DeviceStat).where(DeviceStat.period == period, DeviceStat.at == at, DeviceStat.device_id.in_(ids)))}
        for device_id, reachable, rtt_ms in results:
            row = rows.get(device_id)
            if row is None:
                row = rows[device_id] = DeviceStat(device_id=device_id, period=period, at=at, checks=0, up_checks=0, rtt_count=0)
                db.add(row)
            row.checks += 1
            row.up_checks += 1 if reachable else 0
            if reachable and rtt_ms is not None:
                row.rtt_sum_ms = (row.rtt_sum_ms or 0) + rtt_ms
                row.rtt_count += 1
    db.flush()


def prune(db: Session, now: datetime) -> int:
    removed = 0
    for period, keep in KEEP.items():
        result = db.execute(delete(DeviceStat).where(DeviceStat.period == period, DeviceStat.at < now - keep)
                            .execution_options(synchronize_session=False))
        removed += result.rowcount or 0
    return removed
