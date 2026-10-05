"""Fase 4: stato live dei device.

Per ogni device attivo con un IP di management: ping ICMP e, se il device ha un profilo SNMP (lo salva la
scansione), lettura di ifOperStatus per aggiornare lo stato delle porte. Basta una delle due risposte
per considerarlo raggiungibile (alcuni apparati non rispondono al ping).
"""
import asyncio
import logging
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.discovery import snmp
from app.models import Device, Interface, IPAddress
from app.models.enums import DeviceStatus

logger = logging.getLogger(__name__)

# Device da non controllare: pianificati o dismessi non devono comparire "giù"
SKIPPED_STATUS = {DeviceStatus.PLANNED.value, DeviceStatus.DECOMMISSIONED.value}
_RTT = re.compile(r"time[=<]([\d.]+)\s*ms")


@dataclass
class Target:
    device_id: int
    host: str
    credentials: snmp.Credentials | None = None


@dataclass
class Probe:
    reachable: bool
    rtt_ms: float | None = None
    oper_status: dict[int, str] = field(default_factory=dict)  # ifIndex -> up/down


Prober = Callable[[list[Target]], dict[int, Probe]]


# ---------------------------------------------------------------- controlli di rete
async def ping(host: str, timeout: float) -> float | None:
    """Tempo di risposta in ms, None se non risponde. Senza il comando ping prova una connessione TCP."""
    if shutil.which("ping"):
        flag = "-6" if ":" in host else "-4"
        process = await asyncio.create_subprocess_exec(
            "ping", flag, "-n", "-c", "1", "-W", str(max(1, round(timeout))), host,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await process.communicate()
        if process.returncode != 0:
            return None
        match = _RTT.search(out.decode(errors="replace"))
        return float(match.group(1)) if match else 0.0
    return await _tcp_probe(host, timeout)


async def _tcp_probe(host: str, timeout: float) -> float | None:
    loop = asyncio.get_running_loop()
    for port in (22, 443, 80, 23):
        start = loop.time()
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
            writer.close()
            return (loop.time() - start) * 1000
        except ConnectionRefusedError:
            return (loop.time() - start) * 1000  # ha risposto, anche se la porta è chiusa
        except (OSError, asyncio.TimeoutError):
            continue
    return None


async def _snmp_status(engine: snmp.SnmpEngine, target: Target) -> dict[int, str] | None:
    creds = target.credentials
    transport = await snmp.UdpTransportTarget.create((target.host, creds.port), timeout=creds.timeout, retries=creds.retries)
    session = snmp._Session(engine, target.host, creds, transport)
    if await session.get(snmp.SYS_NAME) is None:
        return None
    statuses = await session.walk(snmp.IF_OPER_STATUS)
    return {index[0]: snmp.OPER_STATUS.get(value, "unknown") for index, value in statuses.items()
            if len(index) == 1 and isinstance(value, int)}


async def probe_all_async(targets: list[Target], concurrency: int, timeout: float) -> dict[int, Probe]:
    engine = snmp.SnmpEngine()
    semaphore = asyncio.Semaphore(concurrency)

    async def one(target: Target) -> tuple[int, Probe]:
        async with semaphore:
            rtt = await ping(target.host, timeout)
            statuses = None
            if target.credentials is not None:
                try:
                    statuses = await _snmp_status(engine, target)
                except Exception as exc:  # un device problematico non deve fermare gli altri
                    logger.debug("%s: SNMP non riuscito (%s)", target.host, exc)
            return target.device_id, Probe(reachable=rtt is not None or statuses is not None, rtt_ms=rtt,
                                           oper_status=statuses or {})

    try:
        results = await asyncio.gather(*(one(t) for t in targets))
    finally:
        engine.close_dispatcher()
    return dict(results)


def probe_all(targets: list[Target]) -> dict[int, Probe]:
    return asyncio.run(probe_all_async(targets, settings.monitor_concurrency, settings.monitor_timeout))


# ---------------------------------------------------------------- database
def _targets(db: Session, device_ids: list[int] | None) -> list[Target]:
    from app.discovery.runner import load_credentials  # import locale: runner importa i servizi

    stmt = (
        select(Device, IPAddress.host)
        .select_from(IPAddress)
        .join(Interface, IPAddress.interface_id == Interface.id)
        .join(Device, Interface.device_id == Device.id)
        .where(IPAddress.is_primary.is_(True), Device.status.not_in(SKIPPED_STATUS))
        .order_by(Device.id)
    )
    if device_ids is not None:
        stmt = stmt.where(Device.id.in_(device_ids))
    targets = []
    for device, host in db.execute(stmt).unique().all():
        creds = None
        if device.snmp_profile_id:
            try:
                found = load_credentials(db, [device.snmp_profile_id])
                creds = found[0] if found else None
            except Exception as exc:  # segreto non decifrabile: resta il ping
                logger.warning("%s: profilo SNMP non utilizzabile (%s)", device.name, exc)
        targets.append(Target(device_id=device.id, host=host, credentials=creds))
    return targets


def check_devices(db: Session, device_ids: list[int] | None = None, prober: Prober | None = None) -> dict:
    """Controlla i device (tutti o quelli indicati) e salva il risultato. Ritorna un riepilogo."""
    targets = _targets(db, device_ids)
    results = (prober or probe_all)(targets) if targets else {}
    now = datetime.now(timezone.utc)
    up = down = 0
    for target in targets:
        result = results.get(target.device_id)
        if result is None:
            continue
        device = db.get(Device, target.device_id)
        if device.reachable is not result.reachable:
            device.reachable_changed_at = now
            if device.reachable is not None:
                logger.info("%s (%s) ora è %s", device.name, target.host, "raggiungibile" if result.reachable else "irraggiungibile")
        device.reachable, device.last_check_at = result.reachable, now
        device.rtt_ms = round(result.rtt_ms, 2) if result.rtt_ms is not None else None
        if result.oper_status:
            for iface in db.scalars(select(Interface).where(Interface.device_id == device.id, Interface.if_index.is_not(None))):
                if iface.if_index in result.oper_status:
                    iface.oper_status = result.oper_status[iface.if_index]
        up, down = up + result.reachable, down + (not result.reachable)
    db.commit()
    return {"checked": up + down, "up": up, "down": down}


def status_summary(db: Session) -> dict:
    devices = db.execute(select(Device.reachable, Device.last_check_at, Device.status)).all()
    monitored = [d for d in devices if d.status not in SKIPPED_STATUS]
    checks = [d.last_check_at for d in monitored if d.last_check_at]
    return {
        "up": sum(1 for d in monitored if d.reachable is True),
        "down": sum(1 for d in monitored if d.reachable is False),
        "unknown": sum(1 for d in monitored if d.reachable is None),
        "last_check_at": max(checks) if checks else None,
        "interval_seconds": settings.monitor_interval_seconds,
    }

