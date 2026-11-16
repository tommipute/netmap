"""Dettagli delle porte letti dal monitor: stato amministrativo, da quando, errori, duplex e PoE."""
import asyncio
import copy
from datetime import datetime, timedelta, timezone

from app.lab.snmprec import snmprec
from app.services.monitor import Details, PoePort, PortDetail, Probe, check_devices, poe_port_map, read_details
from tests.snmp_devices import SW1, SW2
from tests.test_discovery import create, ports_of

UPTIME = 360_000_00  # 100 ore, in centesimi di secondo


class FakeSession:
    """get/walk come snmp._Session, sui dati di un file snmprec."""

    def __init__(self, text: str):
        self.data = {}
        for line in text.splitlines():
            oid, kind, value = line.split("|", 2)
            self.data[tuple(int(p) for p in oid.split("."))] = (
                bytes.fromhex(value) if kind == "4x" else value.encode() if kind == "4"
                else value if kind in ("6", "64") else int(value))

    async def get(self, *oids):
        return {oid: self.data.get(tuple(int(p) for p in oid.split("."))) for oid in oids}

    async def walk(self, oid):
        prefix = tuple(int(p) for p in oid.split("."))
        return {k[len(prefix):]: v for k, v in self.data.items() if k[:len(prefix)] == prefix and len(k) > len(prefix)}


def cisco():
    device = copy.deepcopy(SW1)
    device["system"]["uptime"] = UPTIME
    device["port_counters"] = {1: (UPTIME - 6000, 12, 0, 3, 0), 2: (0, 0, 0, 0, 0)}  # Gi1/0/1 cambiata un minuto fa
    device["duplex"] = {1: 3, 2: 2}
    device["poe"] = {
        "vendor": "cisco",
        "groups": {1: (740, 23), 2: (740, 0)},
        # Gi1/0/1 alimenta un telefono (classe 2, 4,5 W), Gi1/0/2 cerca; ifIndex dalla ENTITY-MIB
        "ports": {(1, 1): (3, 2, 4500, 1), (1, 2): (2, None, 0, 2)},
    }
    return device


def hp():
    device = copy.deepcopy(SW2)
    device["poe"] = {"vendor": "hp", "groups": {1: (370, 13)}, "ports": {(1, 1): (3, 3, 12800, None), (1, 2): (4, None, 0, None)}}
    return device


def test_lettura_cisco():
    details = asyncio.run(read_details(FakeSession(snmprec(cisco()))))
    first, second = details.ports[1], details.ports[2]
    assert (first.admin_status, first.duplex, first.errors) == ("up", "full", (12, 0, 3, 0))
    assert second.admin_status == "down" and second.duplex == "half"
    assert abs((datetime.now(timezone.utc) - first.last_change).total_seconds() - 60) < 5
    assert second.last_change is None  # ifLastChange 0: non si sa
    assert details.poe[(1, 1)] == PoePort(status="delivering", power_class=2, power_mw=4500)
    assert details.poe[(1, 2)] == PoePort(status="searching")
    assert details.poe_if_index == {(1, 1): 1, (1, 2): 2}
    assert (details.poe_budget_w, details.poe_used_w) == (1480, 23)


def test_lettura_hp_e_switch_senza_dettagli():
    details = asyncio.run(read_details(FakeSession(snmprec(hp()))))
    assert details.poe[(1, 1)] == PoePort(status="delivering", power_class=3, power_mw=12800)
    assert details.poe[(1, 2)].status == "fault" and details.poe_if_index == {}
    assert (details.poe_budget_w, details.poe_used_w) == (370, 13)
    assert details.ports[1].duplex is None and details.ports[1].errors is None and details.ports[1].last_change is None

    plain = asyncio.run(read_details(FakeSession(snmprec(SW2))))
    assert plain.poe == {} and plain.poe_budget_w is None


def test_consumo_in_milliwatt():
    device = hp()
    device["poe"]["groups"] = {1: (190, 3800)}  # Netgear: il consumo arriva in mW
    assert asyncio.run(read_details(FakeSession(snmprec(device)))).poe_used_w == 4


def test_porte_poe_per_nome():
    cisco_ports = [(10101, "Gi1/0/1"), (10102, "Gi1/0/2"), (10601, "Te1/1/1"), (11101, "Gi2/0/1"), (1, "Vl1")]
    poe = {(1, 1): None, (1, 2): None, (2, 1): None}
    assert poe_port_map(poe, cisco_ports, {}) == {(1, 1): 10101, (1, 2): 10102, (2, 1): 11101}
    assert poe_port_map(poe, cisco_ports, {(1, 1): 99}) == {(1, 1): 99, (1, 2): 10102, (2, 1): 11101}
    # HP ProCurve: porte "1", "2"; ArubaOS-CX: 1/1/5
    assert poe_port_map({(1, 5): None}, [(5, "5"), (6, "6")], {}) == {(1, 5): 5}
    assert poe_port_map({(1, 5): None}, [(1005, "1/1/5"), (1006, "1/1/6")], {}) == {(1, 5): 1005}
    # Niente nome riconoscibile: ifIndex uguale al numero della porta, solo con un gruppo
    assert poe_port_map({(1, 3): None}, [(3, "port3x"), (4, "uplink")], {}) == {(1, 3): 3}
    assert poe_port_map({(1, 3): None, (2, 3): None}, [(3, "ge-a"), (4, "ge-b")], {}) == {}


def device_with_ports(client):
    site = create(client, "/sites", {"name": "Sede"})
    device = create(client, "/devices", {"name": "sw-poe", "site_id": site["id"]})
    ports = {}
    for name, if_index in (("Gi1/0/1", 1), ("Gi1/0/2", 2), ("Gi1/0/3", 3)):
        ports[name] = create(client, "/interfaces", {"device_id": device["id"], "name": name})
    create(client, "/ip-addresses", {"address": "10.0.0.9/24", "interface_id": ports["Gi1/0/1"]["id"], "is_primary": True})
    return device, ports


def set_if_index(session_factory, ports):
    from app.models import Interface
    with session_factory() as db:
        for if_index, port in enumerate(ports.values(), start=1):
            db.get(Interface, port["id"]).if_index = if_index
        db.commit()


def test_monitor_salva_i_dettagli(client, session_factory):
    device, ports = device_with_ports(client)
    set_if_index(session_factory, ports)
    with session_factory() as db:  # dati di prima del monitor: stato senza data
        from app.models import Interface
        db.get(Interface, ports["Gi1/0/2"]["id"]).oper_changed_at = None
        db.commit()
    long_ago = datetime.now(timezone.utc) - timedelta(days=40)
    details = Details(
        ports={1: PortDetail("up", "full", None, (5, 0, 0, 0)), 2: PortDetail("down", "half", long_ago, (0, 0, 0, 0))},
        poe={(1, 1): PoePort("delivering", 2, 4500), (1, 3): PoePort("fault")},
        poe_budget_w=370, poe_used_w=5,
    )
    probe = {device["id"]: Probe(reachable=True, oper_status={1: "up", 2: "down", 3: "down"}, details=details)}
    with session_factory() as db:
        check_devices(db, prober=lambda targets: probe)

    found = ports_of(client, device["id"])
    first, second, third = found["Gi1/0/1"], found["Gi1/0/2"], found["Gi1/0/3"]
    assert (first["admin_status"], first["duplex"], first["in_errors"], first["errors_at"]) == ("up", "full", 5, None)
    assert (first["poe_status"], first["poe_class"], first["poe_power_mw"]) == ("delivering", 2, 4500)
    assert second["admin_status"] == "down" and second["duplex"] == "half" and second["poe_status"] is None
    # Lo switch sa che è giù da 40 giorni, anche se NetMap l'ha vista adesso
    assert second["oper_changed_at"].startswith(long_ago.date().isoformat())
    assert third["poe_status"] == "fault"
    read = client.get(f"/api/devices/{device['id']}").json()
    assert (read["poe_budget_w"], read["poe_used_w"]) == (370, 5) and read["ports_polled_at"]

    # Gli errori salgono: si segna quando. Se il contatore riparte (switch riavviato) no.
    details.ports[1] = PortDetail("up", "full", None, (9, 0, 0, 0))
    with session_factory() as db:
        check_devices(db, prober=lambda targets: probe)
    first = ports_of(client, device["id"])["Gi1/0/1"]
    assert first["in_errors"] == 9 and first["errors_at"]
    details.ports[1] = PortDetail("up", "full", None, (1, 0, 0, 0))
    with session_factory() as db:
        check_devices(db, prober=lambda targets: probe)
    assert ports_of(client, device["id"])["Gi1/0/1"]["errors_at"] == first["errors_at"]

    # Filtri dell'elenco delle porte: giù da più di 30 giorni, half duplex, errori recenti, PoE
    def names(**params):
        return sorted(i["name"] for i in client.get("/api/interfaces", params={"device_id": device["id"], **params}).json()["items"])
    assert names(down_days=30) == ["Gi1/0/2"]
    assert names(duplex="half") == ["Gi1/0/2"]
    assert names(errors_days=1) == ["Gi1/0/1"]
    assert names(poe_status="delivering") == ["Gi1/0/1"] and names(poe_status="fault") == ["Gi1/0/3"]


def test_dettagli_solo_ogni_tanto(client, session_factory, monkeypatch):
    from app.config import settings
    from app.models import Device
    from app.services import monitor

    device, ports = device_with_ports(client)
    with session_factory() as db:
        assert monitor._details_due(db.get(Device, device["id"]))
        db.get(Device, device["id"]).ports_polled_at = datetime.now(timezone.utc)
        db.commit()
        assert not monitor._details_due(db.get(Device, device["id"]))
        monkeypatch.setattr(settings, "monitor_detail_interval_seconds", 0)
        db.get(Device, device["id"]).ports_polled_at = None
        assert not monitor._details_due(db.get(Device, device["id"]))
