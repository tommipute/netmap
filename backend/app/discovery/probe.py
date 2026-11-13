"""Prova di una scansione su pochi indirizzi: cosa succede su ogni indirizzo, senza salvare niente.

Serve a sistemare community, utenti v3 e ACL prima di lanciare la scansione vera: per ogni indirizzo il ping,
l'esito di ogni profilo con il motivo, e per chi risponde cosa si leggerebbe e se il device c'è già in NetMap.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.discovery import snmp, snmp_rules
from app.discovery.matching import find_device
from app.discovery.report import build_report
from app.discovery.vendors import manufacturer_of
from app.models import DeviceType
from app.services.roles import detect_for

MAX_HOSTS = 256


def describe(db: Session, probe: snmp.HostProbe) -> dict:
    result = {
        "host": probe.host,
        "ping_ms": round(probe.ping_ms, 1) if probe.ping_ms is not None else None,
        "attempts": [{"profile": a.profile, "error": a.error, "answered": a.answered} for a in probe.attempts],
        "error": probe.error,
        "found": None,
    }
    hd = probe.data
    if hd is None:
        return result
    known = db.scalars(select(DeviceType).where(DeviceType.sys_object_id == hd.sys_object_id)).first() \
        if hd.sys_object_id else None
    manufacturer = manufacturer_of(hd)
    detected = detect_for(hd)
    device = find_device(db, serial=hd.serial, sys_name=hd.sys_name, ips=[hd.host, *(ip.address for ip in hd.ips)])
    result["found"] = {
        "profile": hd.profile_name,
        "sys_name": hd.sys_name,
        "sys_descr": hd.sys_descr,
        "sys_object_id": hd.sys_object_id,
        "sys_location": hd.sys_location,
        "manufacturer": manufacturer,
        "model": known.model if known else hd.model,
        "model_known": known is not None,
        "serial": hd.serial,
        "kind": f"{detected.kind.role} ({detected.reason})" if detected else None,
        "interfaces": len(hd.interfaces),
        "ips": len(hd.ips),
        "neighbors": len(hd.neighbors),
        "vlans": len(hd.vlans),
        "members": len(hd.members),
        "fdb": len(hd.fdb),
        "arp": len(hd.arp),
        "problems": hd.problems,
        "device_id": device.id if device else None,
        "device_name": device.name if device else None,
        "report": build_report(hd),
    }
    return result


def run_probe(db: Session, hosts: list[str], credentials: list[snmp.Credentials], rules: list = (),
              prober=None) -> list[dict]:
    """`rules`: regole SNMP attive (righe del database), come nella scansione vera."""
    compiled = [snmp_rules.compile_rule(r) for r in rules]
    probes = (prober or (lambda h, c: snmp.probe_all(h, c, settings.discovery_concurrency, rules=compiled)))(hosts, credentials)
    order = {host: i for i, host in enumerate(hosts)}
    return [describe(db, p) for p in sorted(probes, key=lambda p: order.get(p.host, len(order)))]
