"""Storico delle porte: traffico, errori, tempo su e PoE.

A ogni lettura dei dettagli (monitor, ogni 5 minuti) ogni porta dà un campione = differenza dei contatori dalla
lettura prima. Il campione si somma a tre righe di `port_stats`: quella dei 5 minuti, quella dell'ora e quella del
giorno (ora locale del server). Così le ore e i giorni sono pronti senza ricalcoli, e `prune` toglie solo le righe
vecchie: 5 minuti per 2 giorni, ore per 30 giorni, giorni per un anno.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Interface, PortStat

PERIODS = ("5m", "1h", "1d")
KEEP = {"5m": timedelta(days=2), "1h": timedelta(days=30), "1d": timedelta(days=366)}
STEP = {"5m": 300, "1h": 3600, "1d": 86400}
# Intervallo mostrato -> righe usate
RANGES = {"1d": ("5m", timedelta(days=1)), "2d": ("5m", timedelta(days=2)), "7d": ("1h", timedelta(days=7)),
          "30d": ("1h", timedelta(days=30)), "1y": ("1d", timedelta(days=365))}
# Più di così tra due letture (monitor fermo, device che non rispondeva) non si sa quando è passato il traffico
MAX_GAP = timedelta(minutes=30)
WRAP_32 = 2 ** 32


@dataclass
class Sample:
    interface_id: int
    seconds: int
    in_octets: int | None = None
    out_octets: int | None = None
    errors: int = 0
    discards: int = 0
    up: bool = False
    poe_mw: int | None = None

    @property
    def in_bps(self) -> int | None:
        return None if self.in_octets is None else round(self.in_octets * 8 / self.seconds)

    @property
    def out_bps(self) -> int | None:
        return None if self.out_octets is None else round(self.out_octets * 8 / self.seconds)


def counter_delta(current: int | None, previous: int | None, wrap: int | None = None) -> int | None:
    """Quanto è salito un contatore. None se non si sa: manca un valore o è ripartito (switch riavviato).
    Un contatore a 32 bit che ha fatto il giro (sotto metà dello spazio) si conta, uno a 64 bit no."""
    if current is None or previous is None:
        return None
    if current >= previous:
        return current - previous
    if wrap == WRAP_32 and previous - current > WRAP_32 // 2:
        return current + WRAP_32 - previous
    return None


def make_sample(iface: Interface, seconds: int, octets: tuple[int | None, int | None, int | None] | None,
                errors: tuple | None) -> Sample | None:
    """Campione di una porta prima che i contatori nuovi la sovrascrivano.
    `octets` = (in, out, giro del contatore), `errors` = (errori in, out, scarti in, out)."""
    sample = Sample(iface.id, seconds, up=iface.oper_status == "up", poe_mw=iface.poe_power_mw)
    if octets is not None and (octets[0] is not None or octets[1] is not None):
        sample.in_octets = counter_delta(octets[0], iface.in_octets, octets[2])
        sample.out_octets = counter_delta(octets[1], iface.out_octets, octets[2])
        # contatori ripartiti o prima lettura: il campione non dice niente
        if sample.in_octets is None and sample.out_octets is None:
            return None
    if errors is not None:
        previous = (iface.in_errors, iface.out_errors, iface.in_discards, iface.out_discards)
        deltas = [counter_delta(c, p) or 0 for c, p in zip(errors, previous)]
        sample.errors, sample.discards = deltas[0] + deltas[1], deltas[2] + deltas[3]
    return sample


def bucket(moment: datetime, period: str) -> datetime:
    """Inizio dell'intervallo che contiene `moment`. Il giorno è quello dell'ora locale del server."""
    moment = moment.astimezone(timezone.utc)
    if period == "5m":
        return moment.replace(minute=moment.minute - moment.minute % 5, second=0, microsecond=0)
    if period == "1h":
        return moment.replace(minute=0, second=0, microsecond=0)
    local = moment.astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _add(row: PortStat, sample: Sample) -> None:
    row.seconds = (row.seconds or 0) + sample.seconds
    for name in ("in_octets", "out_octets"):
        value = getattr(sample, name)
        if value is not None:
            setattr(row, name, (getattr(row, name) or 0) + value)
    for name, value in (("in_peak_bps", sample.in_bps), ("out_peak_bps", sample.out_bps)):
        if value is not None:
            setattr(row, name, max(getattr(row, name) or 0, value))
    row.errors = (row.errors or 0) + sample.errors
    row.discards = (row.discards or 0) + sample.discards
    row.up_seconds = (row.up_seconds or 0) + (sample.seconds if sample.up else 0)
    if sample.poe_mw is not None:
        row.poe_mws = (row.poe_mws or 0) + sample.poe_mw * sample.seconds


def record(db: Session, samples: list[Sample], now: datetime) -> None:
    """Somma i campioni (stesso momento, di solito le porte di un device) alle righe di 5 minuti, ora e giorno."""
    if not samples:
        return
    ids = [s.interface_id for s in samples]
    for period in PERIODS:
        at = bucket(now, period)
        rows = {r.interface_id: r for r in db.scalars(
            select(PortStat).where(PortStat.period == period, PortStat.at == at, PortStat.interface_id.in_(ids)))}
        for sample in samples:
            row = rows.get(sample.interface_id)
            if row is None:
                row = PortStat(interface_id=sample.interface_id, period=period, at=at)
                db.add(row)
            _add(row, sample)
    db.flush()  # la lettura dopo nella stessa sessione deve trovare queste righe (la sessione non fa autoflush)


def prune(db: Session, now: datetime) -> int:
    """Toglie le righe più vecchie del periodo in cui servono."""
    removed = 0
    for period, keep in KEEP.items():
        result = db.execute(delete(PortStat).where(PortStat.period == period, PortStat.at < now - keep)
                            .execution_options(synchronize_session=False))
        removed += result.rowcount or 0
    return removed


def series(db: Session, interface_id: int, range_: str, now: datetime | None = None) -> dict:
    """Punti del grafico di una porta: medie per intervallo (bit/s, % su, watt), picchi, errori e scarti."""
    period, span = RANGES[range_]
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(select(PortStat).where(
        PortStat.interface_id == interface_id, PortStat.period == period, PortStat.at >= bucket(now - span, period),
    ).order_by(PortStat.at))
    points = []
    totals = {"seconds": 0, "up_seconds": 0, "in_octets": None, "out_octets": None, "errors": 0, "discards": 0}
    for row in rows:
        seconds = row.seconds or 0
        for name in totals:
            value = getattr(row, name)
            if value is not None:
                totals[name] = (totals[name] or 0) + value
        points.append({
            "at": row.at.replace(tzinfo=row.at.tzinfo or timezone.utc),
            "in_bps": round(row.in_octets * 8 / seconds) if seconds and row.in_octets is not None else None,
            "out_bps": round(row.out_octets * 8 / seconds) if seconds and row.out_octets is not None else None,
            "in_peak_bps": row.in_peak_bps,
            "out_peak_bps": row.out_peak_bps,
            "errors": row.errors or 0,
            "discards": row.discards or 0,
            "up": round(row.up_seconds / seconds, 4) if seconds else None,
            "poe_w": round(row.poe_mws / seconds / 1000, 1) if seconds and row.poe_mws is not None else None,
        })
    return {"range": range_, "period": period, "step": STEP[period], "start": bucket(now - span, period),
            "end": now, "points": points, "in_octets": totals["in_octets"], "out_octets": totals["out_octets"],
            "errors": totals["errors"], "discards": totals["discards"],
            "up": round(totals["up_seconds"] / totals["seconds"], 4) if totals["seconds"] else None}
