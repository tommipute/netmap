"""Problemi rilevati: cose che non vanno nella rete, ricavate da quello che monitor e scansione hanno già letto.

Si calcolano a ogni richiesta, niente tabella. Priorità:
- critical: colpisce tanti utenti o tutta la rete (loop, STP che cambia di continuo);
- high: qualcosa non funziona adesso (err-disable, duplex diversi, IP doppio, PoE guasto, porta che va e viene…);
- medium: degrada o va sistemato con calma (errori, half duplex, velocità diverse, collegamento non documentato…);
- low: da sapere (tanti MAC su una porta di accesso).
I testi li scrive il frontend dal tipo (`kind`) e dai valori (`values`).
Un problema si può silenziare (per sempre o per un po'): resta nell'elenco a parte e non conta più.
"""
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import VLAN, Cable, Device, Endpoint, Interface, ProblemSilence, Site
from app.models.enums import Source
from app.services.monitor import SKIPPED_STATUS, _aware
from app.services.topology import natural_key

SEVERITIES = ("critical", "high", "medium", "low")
KINDS = {
    "loop": "critical",
    "stp_storm": "critical",          # high se è successo nelle ultime 24 ore ma non nell'ultima ora
    "err_disabled": "high",
    "duplex_mismatch": "high",
    "native_vlan_mismatch": "high",
    "duplicate_ip": "high",
    "flapping": "high",
    "poe_fault": "high",
    "poe_budget": "high",             # medium sotto il 95%
    "errors_rising": "medium",
    "half_duplex": "medium",
    "speed_mismatch": "medium",
    "undocumented_link": "medium",
    "stp_blocked": "medium",
    "many_macs": "low",
}
RECENT = timedelta(hours=24)
FLAPS_MIN = 4             # cambi di stato in 24 ore (due volte giù e su)
MANY_MACS = 8             # MAC su una porta di accesso
POE_HIGH, POE_FULL = 0.8, 0.95


@dataclass
class Problem:
    kind: str
    device: Device
    interface: Interface | None = None
    other_device: Device | None = None
    other_interface: Interface | None = None
    severity: str | None = None
    since: datetime | None = None     # da quando succede, se si sa
    seen_at: datetime | None = None   # quando è stato visto l'ultima volta (scansione)
    values: dict = field(default_factory=dict)

    def __post_init__(self):
        self.severity = self.severity or KINDS[self.kind]


def _devices(db: Session) -> dict[int, Device]:
    return {d.id: d for d in db.scalars(select(Device).where(Device.status.not_in(SKIPPED_STATUS)))}


def _connected_devices(db: Session) -> dict[int, set[int]]:
    """Device collegati da un cavo documentato (in entrambe le direzioni)."""
    a, b = Interface.__table__.alias("a"), Interface.__table__.alias("b")
    rows = db.execute(
        select(a.c.device_id, b.c.device_id)
        .select_from(Cable.__table__)
        .join(a, a.c.id == Cable.a_interface_id)
        .join(b, b.c.id == Cable.b_interface_id)
    ).all()
    graph: dict[int, set[int]] = defaultdict(set)
    for first, second in rows:
        if first != second:
            graph[first].add(second)
            graph[second].add(first)
    return graph


def _path(graph: dict[int, set[int]], start: int, end: int) -> bool:
    seen, queue = {start}, deque([start])
    while queue:
        current = queue.popleft()
        if current == end:
            return True
        for nxt in graph.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return False


def _native_vid(iface: Interface, vids: dict[int, int]) -> int | None:
    """VLAN non taggata di una porta access o trunk. La scansione non salva la VLAN 1 di default: un trunk letto via
    SNMP senza VLAN non taggata ha la 1. Una porta documentata a mano senza VLAN non dice niente."""
    if iface.mode not in ("access", "trunk"):
        return None
    if iface.untagged_vlan_id:
        return vids.get(iface.untagged_vlan_id)
    return 1 if iface.mode == "trunk" and iface.source == Source.SNMP.value else None


def _cable_problems(db: Session, devices: dict[int, Device], interfaces: dict[int, Interface]) -> tuple[list[Problem], set[int]]:
    """Confronta i due capi di ogni cavo: duplex, VLAN non taggata, velocità."""
    problems: list[Problem] = []
    mismatched: set[int] = set()  # porte già segnalate per il duplex: niente "half duplex" in più
    vids = dict(db.execute(select(VLAN.id, VLAN.vid)).all())
    for a_id, b_id in db.execute(select(Cable.a_interface_id, Cable.b_interface_id)).all():
        a, b = interfaces.get(a_id), interfaces.get(b_id)
        if a is None or b is None:
            continue
        if a.duplex and b.duplex and a.duplex != b.duplex:
            half, full = (a, b) if a.duplex == "half" else (b, a)
            problems.append(Problem("duplex_mismatch", devices[half.device_id], half, devices[full.device_id], full,
                                    since=_aware(half.oper_changed_at)))
            mismatched |= {a.id, b.id}
        vid_a, vid_b = _native_vid(a, vids), _native_vid(b, vids)
        if vid_a and vid_b and vid_a != vid_b:
            problems.append(Problem("native_vlan_mismatch", devices[a.device_id], a, devices[b.device_id], b,
                                    values={"vlan": vid_a, "other_vlan": vid_b}))
        if (a.oper_status == b.oper_status == "up" and a.speed_mbps and b.speed_mbps and a.speed_mbps != b.speed_mbps):
            problems.append(Problem("speed_mismatch", devices[a.device_id], a, devices[b.device_id], b,
                                    values={"speed": a.speed_mbps, "other_speed": b.speed_mbps}))
    return problems, mismatched


def _shared_problems(interfaces: list[Interface], devices: dict[int, Device], graph) -> list[Problem]:
    """Porte che vedono i MAC di un altro switch: un problema per coppia di switch."""
    pairs: dict[tuple[int, int], dict[int, Interface]] = defaultdict(dict)
    for iface in interfaces:
        if iface.shared_macs and iface.shared_device_id in devices:
            key = tuple(sorted((iface.device_id, iface.shared_device_id)))
            best = pairs[key].get(iface.device_id)
            if best is None or iface.shared_macs > best.shared_macs:
                pairs[key][iface.device_id] = iface
    problems = []
    for (first, second), ports in pairs.items():
        main, other = (first, second) if first in ports else (second, first)
        iface, other_iface = ports[main], ports.get(other)
        # i due switch sono già collegati da cavi documentati: questo è un secondo percorso
        kind = "loop" if _path(graph, first, second) else "undocumented_link"
        mac_list = sorted({mac for port in ports.values() for mac in port.shared_mac_list or []})
        problems.append(Problem(
            kind, devices[main], iface, devices[other], other_iface,
            seen_at=_aware(iface.shared_at),
            values={"macs": max(len(mac_list), *(p.shared_macs for p in ports.values())), "mac_list": mac_list},
        ))
    return problems


def _duplicate_ips(db: Session, devices: dict[int, Device], now: datetime) -> list[Problem]:
    recent = now - RECENT
    duplicated = select(Endpoint.ip).where(Endpoint.ip.is_not(None), Endpoint.ip_seen_at >= recent) \
        .group_by(Endpoint.ip).having(func.count(func.distinct(Endpoint.mac)) > 1)
    by_ip: dict[str, list[Endpoint]] = defaultdict(list)
    for endpoint in db.scalars(select(Endpoint).where(Endpoint.ip.in_(duplicated), Endpoint.ip_seen_at >= recent)
                               .order_by(Endpoint.mac)).unique():
        by_ip[endpoint.ip].append(endpoint)
    problems = []
    for ip, endpoints in by_ip.items():
        located = [e for e in endpoints if e.interface and e.interface.device_id in devices]
        if not located:
            continue
        first = located[0]
        second = located[1] if len(located) > 1 else None
        problems.append(Problem(
            "duplicate_ip", devices[first.interface.device_id], first.interface,
            devices[second.interface.device_id] if second else None, second.interface if second else None,
            seen_at=max(_aware(e.ip_seen_at) for e in endpoints),
            values={"ip": ip, "macs": [e.mac for e in endpoints]},
        ))
    return problems


def find_problems(db: Session, now: datetime | None = None) -> list[Problem]:
    now = now or datetime.now(timezone.utc)
    recent = now - RECENT
    devices = _devices(db)
    if not devices:
        return []
    interfaces = list(db.scalars(select(Interface).where(Interface.device_id.in_(list(devices)))).unique())
    by_id = {i.id: i for i in interfaces}
    problems, mismatched = _cable_problems(db, devices, by_id)
    graph = _connected_devices(db)
    problems += _shared_problems(interfaces, devices, graph)
    problems += _duplicate_ips(db, devices, now)

    cabled = {i for row in db.execute(select(Cable.a_interface_id, Cable.b_interface_id)).all() for i in row}
    lag_cabled = {i.lag_id for i in interfaces if i.lag_id and i.id in cabled}
    shared = {i.id for i in interfaces if i.shared_macs}
    for iface in interfaces:
        device = devices[iface.device_id]
        if iface.err_disabled:
            problems.append(Problem("err_disabled", device, iface, since=_aware(iface.oper_changed_at),
                                    values={"cause": iface.err_disabled}))
        if iface.poe_status == "fault":
            problems.append(Problem("poe_fault", device, iface))
        if iface.flaps and iface.flaps >= FLAPS_MIN and _aware(iface.flaps_since) >= recent:
            problems.append(Problem("flapping", device, iface, since=_aware(iface.flaps_since),
                                    values={"count": iface.flaps}))
        if iface.errors_at and _aware(iface.errors_at) >= recent:
            problems.append(Problem("errors_rising", device, iface, seen_at=_aware(iface.errors_at),
                                    values={"in": iface.in_errors, "out": iface.out_errors}))
        if iface.duplex == "half" and iface.oper_status != "down" and iface.id not in mismatched:
            problems.append(Problem("half_duplex", device, iface, since=_aware(iface.oper_changed_at)))
        # bloccata da STP ma senza un cavo verso un altro apparato: c'è un percorso doppio che non si conosce
        if iface.stp_state == "blocking" and iface.id not in cabled and iface.id not in lag_cabled:
            problems.append(Problem("stp_blocked", device, iface))

    week = now - timedelta(days=7)
    for interface_id, macs in db.execute(
        select(Endpoint.interface_id, func.max(Endpoint.macs_on_port))
        .where(Endpoint.interface_id.is_not(None), Endpoint.last_seen_at >= week)
        .group_by(Endpoint.interface_id).having(func.max(Endpoint.macs_on_port) >= MANY_MACS)
    ).all():
        iface = by_id.get(interface_id)
        if iface is not None and iface.id not in shared:
            problems.append(Problem("many_macs", devices[iface.device_id], iface, values={"macs": macs}))

    for device in devices.values():
        storm = _aware(device.stp_storm_at)
        if storm and storm >= recent:
            problems.append(Problem("stp_storm", device, severity="critical" if now - storm < timedelta(hours=1) else "high",
                                    seen_at=storm, values={"changes": device.stp_top_changes}))
        if device.poe_budget_w and device.poe_used_w is not None:
            ratio = device.poe_used_w / device.poe_budget_w
            if ratio >= POE_HIGH:
                problems.append(Problem("poe_budget", device, severity="high" if ratio >= POE_FULL else "medium",
                                        values={"used": device.poe_used_w, "budget": device.poe_budget_w}))
    return problems


def problem_key(kind: str, device_id: int, interface_id: int | None, ip: str | None = None) -> str:
    """Cosa identifica un problema per silenziarlo: tipo, device, porta e, per gli IP doppi, l'IP."""
    return f"{kind}:{device_id}:{interface_id or ''}" + (f":{ip}" if kind == "duplicate_ip" and ip else "")


def _key(problem: Problem) -> str:
    return problem_key(problem.kind, problem.device.id, problem.interface.id if problem.interface else None,
                       problem.values.get("ip"))


def active_silences(db: Session, now: datetime | None = None) -> dict[str, ProblemSilence]:
    """Silenziamenti in corso (quelli scaduti si cancellano quando se ne crea uno nuovo)."""
    now = now or datetime.now(timezone.utc)
    return {s.key: s for s in db.scalars(select(ProblemSilence)) if s.until is None or _aware(s.until) > now}


def silence_problem(db: Session, key: str, note: str | None, days: int | None, username: str | None) -> ProblemSilence:
    """Silenzia un problema che c'è adesso (ValueError se non c'è); se era già silenziato cambia nota e scadenza."""
    now = datetime.now(timezone.utc)
    problem = next((p for p in find_problems(db, now) if _key(p) == key), None)
    if problem is None:
        raise ValueError("Il problema non c'è più: ricarica la pagina")
    for old in db.scalars(select(ProblemSilence).where(ProblemSilence.until <= now)):
        db.delete(old)
    silence = db.scalar(select(ProblemSilence).where(ProblemSilence.key == key))
    if silence is None:
        silence = ProblemSilence(key=key, kind=problem.kind, device_id=problem.device.id,
                                 interface_id=problem.interface.id if problem.interface else None)
        db.add(silence)
    silence.note = (note or "").strip() or None
    silence.until = now + timedelta(days=days) if days else None
    silence.created_by, silence.created_at = username, now
    db.commit()
    return silence


def _silence(silence: ProblemSilence | None) -> dict | None:
    if silence is None:
        return None
    return {"id": silence.id, "note": silence.note, "until": _aware(silence.until), "created_by": silence.created_by,
            "created_at": _aware(silence.created_at)}


def _row(problem: Problem, sites: dict[int, str], silence: ProblemSilence | None = None) -> dict:
    device, iface = problem.device, problem.interface
    other, other_iface = problem.other_device, problem.other_interface
    return {
        "key": _key(problem),
        "kind": problem.kind,
        "severity": problem.severity,
        "device_id": device.id,
        "device_name": device.name,
        "site_id": device.site_id,
        "site_name": sites.get(device.site_id),
        "interface_id": iface.id if iface else None,
        "interface_name": iface.name if iface else None,
        "other_device_id": other.id if other else None,
        "other_device_name": other.name if other else None,
        "other_interface_id": other_iface.id if other_iface else None,
        "other_interface_name": other_iface.name if other_iface else None,
        "since": problem.since,
        "seen_at": problem.seen_at,
        "values": problem.values,
        "silenced": _silence(silence),
    }


def problem_list(db: Session, severity: str | None = None, kind: str | None = None, site_id: int | None = None,
                 device_id: int | None = None) -> dict:
    """Problemi filtrati, in ordine di priorità, e quanti ce ne sono per priorità (senza il filtro della priorità).
    Quelli silenziati non contano e stanno a parte, in `silenced`."""
    problems = find_problems(db)
    silences = active_silences(db)
    if kind:
        problems = [p for p in problems if p.kind == kind]
    if site_id is not None:
        problems = [p for p in problems if p.device.site_id == site_id]
    if device_id is not None:
        problems = [p for p in problems if device_id in (p.device.id, p.other_device.id if p.other_device else None)]
    silenced = [p for p in problems if _key(p) in silences]
    problems = [p for p in problems if _key(p) not in silences]
    counts = {level: 0 for level in SEVERITIES}
    for p in problems:
        counts[p.severity] += 1
    if severity:
        problems = [p for p in problems if p.severity == severity]
    order = lambda p: (SEVERITIES.index(p.severity), natural_key(p.device.name),  # noqa: E731
                       natural_key(p.interface.name) if p.interface else [], p.kind)
    problems.sort(key=order)
    silenced.sort(key=order)
    sites = dict(db.execute(select(Site.id, Site.name)).all())
    return {"total": len(problems), "counts": counts, "items": [_row(p, sites) for p in problems],
            "silenced": [_row(p, sites, silences[_key(p)]) for p in silenced]}
