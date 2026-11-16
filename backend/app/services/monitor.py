"""Fase 4: stato live dei device.

Per ogni device attivo con un IP di management: ping ICMP e, se il device ha un profilo SNMP (lo salva la
scansione), lettura di ifOperStatus per aggiornare lo stato delle porte. Basta una delle due risposte
per considerarlo raggiungibile (alcuni apparati non rispondono al ping).

Ogni MONITOR_DETAIL_INTERVAL_SECONDS legge anche i dettagli delle porte: stato amministrativo, da quando sono
su o giù (ifLastChange), contatori di errori e scarti, duplex (EtherLike-MIB) e PoE (POWER-ETHERNET-MIB, più il
consumo per porta dalle MIB di Cisco e HP). Le porte PoE hanno un loro indice (gruppo, porta): vedi poe_port_map.
"""
import asyncio
import logging
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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
_NUMBERS = re.compile(r"\d+")

SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
IF_LAST_CHANGE = "1.3.6.1.2.1.2.2.1.9"
IF_IN_DISCARDS, IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.13", "1.3.6.1.2.1.2.2.1.14"
IF_OUT_DISCARDS, IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.19", "1.3.6.1.2.1.2.2.1.20"
DOT3_DUPLEX = "1.3.6.1.2.1.10.7.2.1.19"                # dot3StatsDuplexStatus, indice = ifIndex
PETH_PORT_DETECTION = "1.3.6.1.2.1.105.1.1.1.6"        # pethPsePortDetectionStatus, indice = gruppo.porta
PETH_PORT_CLASS = "1.3.6.1.2.1.105.1.1.1.10"           # pethPsePortPowerClassifications
PETH_MAIN_POWER = "1.3.6.1.2.1.105.1.3.1.1.2"          # pethMainPsePower (W), indice = gruppo
PETH_MAIN_CONSUMPTION = "1.3.6.1.2.1.105.1.3.1.1.4"    # pethMainPseConsumptionPower (W)
CISCO_POE_POWER = "1.3.6.1.4.1.9.9.402.1.2.1.9"        # cpeExtPsePortPwrConsumption (mW)
CISCO_POE_ENTITY = "1.3.6.1.4.1.9.9.402.1.2.1.11"      # cpeExtPsePortEntPhyIndex
HP_POE_POWER = "1.3.6.1.4.1.11.2.14.11.1.9.1.1.1.3"    # hpicfPoePethPsePortPower (mW)
IF_INDEX = "1.3.6.1.2.1.2.2.1.1"
STP_TIME_SINCE_CHANGE = "1.3.6.1.2.1.17.2.3.0"          # dot1dStpTimeSinceTopologyChange (centesimi)
STP_TOP_CHANGES = "1.3.6.1.2.1.17.2.4.0"                # dot1dStpTopChanges
STP_PORT_STATE = "1.3.6.1.2.1.17.2.15.1.3"              # dot1dStpPortState, indice = porta bridge
CISCO_ERR_DISABLE = "1.3.6.1.4.1.9.9.548.1.3.1.1.2"    # cErrDisableIfStatusCause, indice = ifIndex.vlan
ENT_ALIAS_MAPPING = "1.3.6.1.2.1.47.1.3.2.1.2"         # entAliasMappingIdentifier: entità -> OID con l'ifIndex
ADMIN_STATUS = {1: "up", 2: "down", 3: "testing"}
DUPLEX = {2: "half", 3: "full"}
POE_STATUS = {1: "disabled", 2: "searching", 3: "delivering", 4: "fault", 5: "test", 6: "fault"}
STP_STATE = {1: "disabled", 2: "blocking", 3: "listening", 4: "learning", 5: "forwarding", 6: "broken"}
# CISCO-ERR-DISABLE-MIB, CErrDisableFeatureID: le cause più comuni (le altre restano col numero)
ERR_DISABLE_CAUSE = {
    1: "udld", 2: "bpduGuard", 3: "channelMisconfig", 4: "pagpFlap", 5: "dtpFlap", 6: "linkFlap", 7: "l2ptGuard",
    8: "dot1xSecurityViolation", 9: "portSecurityViolation", 10: "gbicInvalid", 11: "dhcpRateLimit",
    12: "unicastFlood", 14: "stormControl", 15: "inlinePower", 16: "arpInspection", 17: "portLoopback",
    19: "macLimit", 36: "other",
}
FLAP_WINDOW = timedelta(hours=24)


@dataclass
class Target:
    device_id: int
    host: str
    credentials: snmp.Credentials | None = None
    details: bool = False  # leggere anche i dettagli delle porte


@dataclass
class PortDetail:
    admin_status: str | None = None
    duplex: str | None = None
    last_change: datetime | None = None  # dallo switch: ifLastChange rispetto a sysUpTime
    errors: tuple[int | None, int | None, int | None, int | None] | None = None  # errori in/out, scarti in/out
    last_change_ticks: int | None = None  # ifLastChange così com'è


@dataclass
class PoePort:
    status: str | None = None
    power_class: int | None = None
    power_mw: int | None = None


@dataclass
class Details:
    ports: dict[int, PortDetail] = field(default_factory=dict)          # ifIndex -> dettagli
    poe: dict[tuple[int, int], PoePort] = field(default_factory=dict)   # (gruppo, porta) -> PoE
    poe_if_index: dict[tuple[int, int], int] = field(default_factory=dict)  # dalla ENTITY-MIB (Cisco)
    poe_budget_w: int | None = None
    poe_used_w: int | None = None
    stp_top_changes: int | None = None
    stp_changed_at: datetime | None = None
    stp_ports: dict[int, str] = field(default_factory=dict)      # ifIndex -> stato STP
    err_disabled: dict[int, str] = field(default_factory=dict)   # ifIndex -> causa


@dataclass
class Probe:
    reachable: bool
    rtt_ms: float | None = None
    oper_status: dict[int, str] = field(default_factory=dict)  # ifIndex -> up/down
    details: Details | None = None  # solo quando è il momento (vedi Target.details)


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


async def _snmp_status(engine: snmp.SnmpEngine, target: Target) -> tuple[dict[int, str], Details | None] | None:
    creds = target.credentials
    transport = await snmp.UdpTransportTarget.create((target.host, creds.port), timeout=creds.timeout, retries=creds.retries)
    session = snmp._Session(engine, target.host, creds, transport)
    if await session.get(snmp.SYS_NAME) is None:
        return None
    statuses = await session.walk(snmp.IF_OPER_STATUS)
    oper = {index[0]: snmp.OPER_STATUS.get(value, "unknown") for index, value in statuses.items()
            if len(index) == 1 and isinstance(value, int)}
    return oper, (await read_details(session) if target.details else None)


def _by_index(column: dict[tuple[int, ...], object], size: int = 1) -> dict:
    """Valori interi di una colonna, per indice di `size` numeri (1 = ifIndex, 2 = gruppo.porta PoE)."""
    key = (lambda i: i[0]) if size == 1 else (lambda i: i)
    return {key(index): value for index, value in column.items() if len(index) == size and isinstance(value, int)}


async def read_details(session) -> Details:
    """Dettagli delle porte e PoE. `session` ha get(oid) e walk(oid) come snmp._Session."""
    now = datetime.now(timezone.utc)
    uptime = ((await session.get(SYS_UPTIME)) or {}).get(SYS_UPTIME)
    admin = _by_index(await session.walk(snmp.IF_ADMIN_STATUS))
    last_change = _by_index(await session.walk(IF_LAST_CHANGE))
    counters = [_by_index(await session.walk(oid)) for oid in (IF_IN_ERRORS, IF_OUT_ERRORS, IF_IN_DISCARDS, IF_OUT_DISCARDS)]
    duplex = _by_index(await session.walk(DOT3_DUPLEX))
    details = Details()
    for if_index in set(admin) | set(duplex) | set(counters[0]):
        port = PortDetail(admin_status=ADMIN_STATUS.get(admin.get(if_index)), duplex=DUPLEX.get(duplex.get(if_index)))
        ticks = last_change.get(if_index)
        # 0 = prima dell'avvio dell'agente: non dice niente (e certi apparati lo danno sempre)
        if isinstance(uptime, int) and ticks and 0 < ticks <= uptime:
            port.last_change = now - timedelta(seconds=(uptime - ticks) / 100)
            port.last_change_ticks = ticks
        values = tuple(c.get(if_index) for c in counters)
        if any(v is not None for v in values):
            port.errors = values
        details.ports[if_index] = port

    detection = _by_index(await session.walk(PETH_PORT_DETECTION), 2)
    if detection:
        classes = _by_index(await session.walk(PETH_PORT_CLASS), 2)
        power = _by_index(await session.walk(CISCO_POE_POWER), 2) or _by_index(await session.walk(HP_POE_POWER), 2)
        for key, value in detection.items():
            status = POE_STATUS.get(value)
            details.poe[key] = PoePort(
                status=status,
                power_class=classes[key] - 1 if status == "delivering" and classes.get(key, 0) >= 1 else None,
                power_mw=power.get(key) if status == "delivering" else None,
            )
        entities = _by_index(await session.walk(CISCO_POE_ENTITY), 2)
        if entities:
            aliases = await session.walk(ENT_ALIAS_MAPPING)
            by_entity = {index[0]: value for index, value in aliases.items() if isinstance(value, str)}
            for key, entity in entities.items():
                target = by_entity.get(entity, "")
                if target.startswith(IF_INDEX + "."):
                    details.poe_if_index[key] = int(target.rsplit(".", 1)[1])
    budget = _by_index(await session.walk(PETH_MAIN_POWER))
    used = _by_index(await session.walk(PETH_MAIN_CONSUMPTION))
    if budget:
        details.poe_budget_w = sum(budget.values())
        consumed = sum(used.values()) if used else None
        # qualche switch (Netgear) dà il consumo in mW invece che in W
        if consumed is not None and consumed > details.poe_budget_w >= consumed / 1000:
            consumed = round(consumed / 1000)
        details.poe_used_w = consumed

    stp = (await session.get(STP_TOP_CHANGES, STP_TIME_SINCE_CHANGE)) or {}
    if isinstance(stp.get(STP_TOP_CHANGES), int):
        details.stp_top_changes = stp[STP_TOP_CHANGES]
        if isinstance(stp.get(STP_TIME_SINCE_CHANGE), int) and details.stp_top_changes:
            details.stp_changed_at = now - timedelta(seconds=stp[STP_TIME_SINCE_CHANGE] / 100)
        states = _by_index(await session.walk(STP_PORT_STATE))
        if states:
            base_ports = _by_index(await session.walk(snmp.DOT1D_BASE_PORT_IF_INDEX))
            for base_port, state in states.items():
                details.stp_ports[base_ports.get(base_port, base_port)] = STP_STATE.get(state)
    for index, cause in (await session.walk(CISCO_ERR_DISABLE)).items():
        if len(index) == 2 and isinstance(cause, int):
            details.err_disabled[index[0]] = ERR_DISABLE_CAUSE.get(cause, str(cause))
    return details


def poe_port_map(poe_ports, interfaces: list[tuple[int, str]], known: dict[tuple[int, int], int]) -> dict[tuple[int, int], int]:
    """(gruppo, porta) PoE -> ifIndex. Prima quello che dice lo switch (ENTITY-MIB, Cisco), poi il nome della porta:
    gruppo = primo numero e porta = ultimo (Gi1/0/5, 1/1/5; preferiti quelli con gli zeri in mezzo, così Gi1/0/1 vince
    su Te1/1/1), o solo il numero con un gruppo (HP: "5"); infine l'ifIndex uguale al numero della porta."""
    numbers = {if_index: [int(n) for n in _NUMBERS.findall(name)] for if_index, name in interfaces}
    groups = {group for group, _ in poe_ports}
    result = {}
    for key in poe_ports:
        if key in known:
            result[key] = known[key]
            continue
        group, port = key
        candidates = [i for i, n in numbers.items()
                      if (len(n) >= 2 and n[0] == group and n[-1] == port) or (n == [port] and len(groups) == 1)]
        if len(candidates) > 1:
            candidates = [i for i in candidates if all(x == 0 for x in numbers[i][1:-1])]
        if len(candidates) == 1:
            result[key] = candidates[0]
        elif not candidates and port in numbers and len(groups) == 1:
            result[key] = port
    return result


async def probe_all_async(targets: list[Target], concurrency: int, timeout: float) -> dict[int, Probe]:
    engine = snmp.SnmpEngine()
    semaphore = asyncio.Semaphore(concurrency)

    async def one(target: Target) -> tuple[int, Probe]:
        async with semaphore:
            rtt = await ping(target.host, timeout)
            answer = None
            if target.credentials is not None:
                try:
                    answer = await _snmp_status(engine, target)
                except Exception as exc:  # un device problematico non deve fermare gli altri
                    logger.debug("%s: SNMP non riuscito (%s)", target.host, exc)
            statuses, details = answer or ({}, None)
            return target.device_id, Probe(reachable=rtt is not None or answer is not None, rtt_ms=rtt,
                                           oper_status=statuses, details=details)

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
        targets.append(Target(device_id=device.id, host=host, credentials=creds, details=creds is not None and _details_due(device)))
    return targets


def _aware(moment: datetime | None) -> datetime | None:
    return moment.replace(tzinfo=timezone.utc) if moment is not None and moment.tzinfo is None else moment


def _details_due(device: Device) -> bool:
    interval = settings.monitor_detail_interval_seconds
    if interval <= 0:
        return False
    last = _aware(device.ports_polled_at)
    # un po' di margine: il controllo dopo l'intervallo può arrivare qualche secondo prima
    return last is None or (datetime.now(timezone.utc) - last).total_seconds() >= interval - 30


def count_flaps(iface: Interface, now: datetime, changes: int = 1) -> None:
    """Cambi di stato della porta nelle ultime 24 ore (la finestra riparte al primo cambio dopo 24 ore)."""
    since = _aware(iface.flaps_since)
    if since is None or now - since > FLAP_WINDOW:
        iface.flaps, iface.flaps_since = 0, now
    iface.flaps = (iface.flaps or 0) + changes


def save_details(db: Session, device: Device, details: Details, now: datetime) -> None:
    interfaces = list(db.scalars(select(Interface).where(Interface.device_id == device.id, Interface.if_index.is_not(None))))
    read_before = device.ports_polled_at is not None
    poe_map = poe_port_map(details.poe, [(i.if_index, i.name) for i in interfaces], details.poe_if_index)
    poe_by_index = {if_index: details.poe[key] for key, if_index in poe_map.items()}
    for iface in interfaces:
        port = details.ports.get(iface.if_index)
        if port is not None:
            iface.admin_status, iface.duplex = port.admin_status, port.duplex
            changed = _aware(iface.oper_changed_at)
            # lo switch sa da quando la porta è così anche se NetMap l'ha vista dopo (prima scansione, monitor spento)
            if port.last_change is not None and (changed is None or port.last_change < changed):
                iface.oper_changed_at = port.last_change
            # cambiata dopo l'ultima volta che NetMap l'ha vista cambiare, ma lo stato è lo stesso: è scesa e risalita
            # (o il contrario) tra due controlli. Deve cambiare anche ifLastChange: con sysUpTime fermo (simulatori,
            # agenti difettosi) l'orario calcolato avanza da solo a ogni lettura
            elif (read_before and port.last_change is not None and port.last_change - changed > timedelta(minutes=2)
                  and iface.last_change_ticks is not None and port.last_change_ticks != iface.last_change_ticks):
                count_flaps(iface, now, 2)
                iface.oper_changed_at = port.last_change
            iface.last_change_ticks = port.last_change_ticks
            if port.errors is not None:
                in_err, out_err = port.errors[0], port.errors[1]
                grew = (in_err or 0) > (iface.in_errors or 0) or (out_err or 0) > (iface.out_errors or 0)
                # la prima lettura non dice se gli errori sono recenti; un contatore che scende = switch riavviato
                if grew and (iface.in_errors is not None or iface.out_errors is not None):
                    iface.errors_at = now
                iface.in_errors, iface.out_errors, iface.in_discards, iface.out_discards = port.errors
        poe = poe_by_index.get(iface.if_index)
        iface.poe_status = poe.status if poe else None
        iface.poe_class = poe.power_class if poe else None
        iface.poe_power_mw = poe.power_mw if poe else None
        iface.err_disabled = details.err_disabled.get(iface.if_index)
        iface.stp_state = details.stp_ports.get(iface.if_index)
    device.poe_budget_w, device.poe_used_w = details.poe_budget_w, details.poe_used_w
    _save_stp(device, details, now)
    device.ports_polled_at = now


# Topologia STP che cambia di continuo: almeno STP_STORM_CHANGES cambi tra due letture, al ritmo di STP_STORM_PER_HOUR
STP_STORM_CHANGES, STP_STORM_PER_HOUR = 5, 30


def _save_stp(device: Device, details: Details, now: datetime) -> None:
    previous, last = device.stp_top_changes, _aware(device.ports_polled_at)
    current = details.stp_top_changes
    if current is not None and previous is not None and last is not None and current >= previous:
        delta, hours = current - previous, max((now - last).total_seconds() / 3600, 1 / 60)
        if delta >= STP_STORM_CHANGES and delta / hours >= STP_STORM_PER_HOUR:
            device.stp_storm_at = now
    device.stp_top_changes, device.stp_changed_at = current, details.stp_changed_at


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
                    status = result.oper_status[iface.if_index]
                    if iface.oper_status is not None and status != iface.oper_status:
                        count_flaps(iface, now)
                    iface.oper_status = status
        if result.details is not None:
            save_details(db, device, result.details, now)
        up, down = up + result.reachable, down + (not result.reachable)
    db.commit()
    return {"checked": up + down, "up": up, "down": down}


# ---------------------------------------------------------------- filtri dell'elenco delle porte
def filter_down_days(db: Session, stmt, days: int):
    """Porte non su da almeno `days` giorni: quelle libere davvero."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    return stmt.where(Interface.oper_status.is_not(None), Interface.oper_status != "up", Interface.oper_changed_at <= since)


def filter_errors_days(db: Session, stmt, days: int):
    """Porte i cui contatori di errori sono saliti negli ultimi `days` giorni."""
    return stmt.where(Interface.errors_at >= datetime.now(timezone.utc) - timedelta(days=days))


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

