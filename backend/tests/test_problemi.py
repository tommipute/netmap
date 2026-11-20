"""Problemi rilevati: STP, err-disable, porte che vanno e vengono, hub tra due switch, confronto dei capi dei cavi."""
import asyncio
import copy
from datetime import datetime, timedelta, timezone

from app.lab.snmprec import snmprec
from app.services.monitor import Details, PortDetail, Probe, check_devices, read_details
from tests.snmp_devices import PC_A_MAC, SW1, SW2
from tests.test_discovery import (  # noqa: F401  (setup è una fixture)
    SW1_HOST, SW2_HOST, approve_all, create, device_named, pending, ports_of, scan, setup,
)
from tests.test_porte_dettagli import FakeSession, device_with_ports, set_if_index

HUB = ["00:50:56:00:01:01", "00:50:56:00:01:02", "00:50:56:00:01:03"]


def problems(client, **params):
    return client.get("/api/problems", params=params).json()


def kinds(client, **params):
    return sorted((p["kind"], p["severity"], p["device_name"], p["interface_name"]) for p in problems(client, **params)["items"])


def test_lettura_stp_ed_err_disable():
    device = copy.deepcopy(SW1)
    device["stp"] = {"changes": 42, "since": 360000, "ports": {1: 5, 2: 2, 9: 5}}
    device["err_disabled"] = {1: 2, 9: 99}
    details = asyncio.run(read_details(FakeSession(snmprec(device))))
    assert details.stp_top_changes == 42
    assert abs((datetime.now(timezone.utc) - details.stp_changed_at).total_seconds() - 3600) < 5
    assert details.stp_ports == {1: "forwarding", 2: "blocking", 9: "forwarding"}
    assert details.err_disabled == {1: "bpduGuard", 9: "99"}  # causa sconosciuta: resta il numero

    plain = asyncio.run(read_details(FakeSession(snmprec(SW2))))
    assert plain.stp_top_changes is None and plain.stp_ports == {} and plain.err_disabled == {}


def test_monitor_porte_che_vanno_e_vengono_e_stp(client, session_factory):
    from app.models import Device, Interface
    device, ports = device_with_ports(client)
    set_if_index(session_factory, ports)
    details = Details(ports={1: PortDetail("up"), 2: PortDetail("up")}, stp_top_changes=100)
    probe = {device["id"]: Probe(reachable=True, oper_status={1: "up", 2: "up", 3: "down"}, details=details)}

    def check():
        with session_factory() as db:
            check_devices(db, prober=lambda targets: probe)

    check()
    for status in ("down", "up", "down", "up"):  # Gi1/0/1 cambia quattro volte
        probe[device["id"]].oper_status[1] = status
        check()
    with session_factory() as db:
        first = db.get(Interface, ports["Gi1/0/1"]["id"])
        assert first.flaps == 4 and first.flaps_since is not None
    assert ("flapping", "high", "sw-poe", "Gi1/0/1") in kinds(client)

    # Gi1/0/2: per NetMap su da sempre, ma lo switch dice che è cambiata due minuti e mezzo fa = è scesa e risalita
    def read_port_2(ticks, ago):
        details.ports[2] = PortDetail("up", last_change=datetime.now(timezone.utc) - ago, last_change_ticks=ticks)
        with session_factory() as db:
            db.get(Device, device["id"]).ports_polled_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
            check_devices(db, prober=lambda targets: probe)
            return db.get(Interface, ports["Gi1/0/2"]["id"]).flaps

    assert read_port_2(1000, timedelta(days=3)) is None
    # sysUpTime fermo (simulatore): ifLastChange è lo stesso, l'orario calcolato avanza da solo. Non è un cambio
    assert read_port_2(1000, timedelta(days=2)) is None
    assert read_port_2(2000, timedelta(seconds=150)) == 2

    # STP: 3 cambi in 5 minuti sono pochi, 20 sono una tempesta
    for changes, storm in ((103, False), (123, True)):
        details.stp_top_changes = changes
        with session_factory() as db:
            db.get(Device, device["id"]).ports_polled_at = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
            check_devices(db, prober=lambda targets: probe)
            assert (db.get(Device, device["id"]).stp_storm_at is not None) is storm
    assert ("stp_storm", "critical", "sw-poe", None) in kinds(client)


def test_problemi_dai_capi_dei_cavi_e_dalle_porte(client, session_factory):
    from app.models import Device, Endpoint, Interface
    site = create(client, "/sites", {"name": "Sede"})
    vlan1 = create(client, "/vlans", {"vid": 1, "name": "default"})
    vlan99 = create(client, "/vlans", {"vid": 99, "name": "mgmt"})
    a = create(client, "/devices", {"name": "sw-a", "site_id": site["id"]})
    b = create(client, "/devices", {"name": "sw-b", "site_id": site["id"]})
    port = {}
    for device in (a, b):
        for name in ("1", "2", "3", "4", "5"):
            port[device["name"], name] = create(client, "/interfaces", {"device_id": device["id"], "name": name})
    create(client, "/cables", {"a_interface_id": port["sw-a", "1"]["id"], "b_interface_id": port["sw-b", "1"]["id"]})
    create(client, "/cables", {"a_interface_id": port["sw-a", "2"]["id"], "b_interface_id": port["sw-b", "2"]["id"]})
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        def iface(device, name):
            return db.get(Interface, port[device, name]["id"])
        # cavo 1: half da una parte e full dall'altra, VLAN non taggata diversa
        iface("sw-a", "1").duplex, iface("sw-b", "1").duplex = "full", "half"
        iface("sw-a", "1").mode, iface("sw-a", "1").untagged_vlan_id = "trunk", vlan1["id"]
        iface("sw-b", "1").mode, iface("sw-b", "1").untagged_vlan_id = "trunk", vlan99["id"]
        # cavo 2: velocità diverse con il link su
        for dev, speed in (("sw-a", 1000), ("sw-b", 100)):
            iface(dev, "2").speed_mbps, iface(dev, "2").oper_status = speed, "up"
        iface("sw-a", "3").err_disabled = "bpduGuard"
        iface("sw-a", "3").poe_status = "fault"
        iface("sw-a", "4").duplex, iface("sw-a", "4").oper_status = "half", "up"
        iface("sw-a", "4").errors_at, iface("sw-a", "4").in_errors = now - timedelta(hours=2), 50
        iface("sw-a", "5").stp_state = "blocking"       # bloccata senza cavo: percorso che non si conosce
        iface("sw-b", "2").stp_state = "blocking"       # bloccata su un cavo documentato: ridondanza voluta
        iface("sw-b", "3").errors_at = now - timedelta(days=3)  # errori vecchi: niente
        iface("sw-b", "4").flaps, iface("sw-b", "4").flaps_since = 6, now - timedelta(days=2)  # finestra scaduta
        db.get(Device, a["id"]).poe_budget_w, db.get(Device, a["id"]).poe_used_w = 370, 300
        db.get(Device, b["id"]).poe_budget_w, db.get(Device, b["id"]).poe_used_w = 370, 360
        db.get(Device, b["id"]).stp_storm_at = now - timedelta(hours=5)
        # 9 MAC dietro la 3 di sw-b; due MAC con lo stesso IP
        for i in range(9):
            db.add(Endpoint(mac=f"00:50:56:00:09:0{i}", interface_id=port["sw-b", "3"]["id"], macs_on_port=9, last_seen_at=now))
        for i, where in enumerate((("sw-b", "5"), ("sw-a", "5"))):
            db.add(Endpoint(mac=f"00:50:56:00:08:0{i}", interface_id=port[where]["id"], macs_on_port=1,
                            last_seen_at=now, ip="10.0.0.50", ip_seen_at=now - timedelta(hours=i)))
        db.add(Endpoint(mac="00:50:56:00:08:09", interface_id=port["sw-b", "5"]["id"], ip="10.0.0.60",
                        ip_seen_at=now - timedelta(days=2), last_seen_at=now))
        db.commit()

    assert kinds(client) == sorted([
        ("duplex_mismatch", "high", "sw-b", "1"),
        ("native_vlan_mismatch", "high", "sw-a", "1"),
        ("speed_mismatch", "medium", "sw-a", "2"),
        ("err_disabled", "high", "sw-a", "3"),
        ("poe_fault", "high", "sw-a", "3"),
        ("half_duplex", "medium", "sw-a", "4"),
        ("errors_rising", "medium", "sw-a", "4"),
        ("stp_blocked", "medium", "sw-a", "5"),
        ("many_macs", "low", "sw-b", "3"),
        ("duplicate_ip", "high", "sw-b", "5"),
        ("poe_budget", "medium", "sw-a", None),
        ("poe_budget", "high", "sw-b", None),
        ("stp_storm", "high", "sw-b", None),
    ])
    found = problems(client)
    assert found["counts"] == {"critical": 0, "high": 7, "medium": 5, "low": 1}
    assert [p["severity"] for p in found["items"]] == sorted((p["severity"] for p in found["items"]),
                                                            key=["critical", "high", "medium", "low"].index)
    by_kind = {p["kind"]: p for p in found["items"]}
    assert by_kind["native_vlan_mismatch"]["values"] == {"vlan": 1, "other_vlan": 99}
    assert by_kind["duplex_mismatch"]["other_interface_name"] == "1" and by_kind["duplex_mismatch"]["other_device_name"] == "sw-a"
    assert by_kind["err_disabled"]["values"] == {"cause": "bpduGuard"}
    assert by_kind["duplicate_ip"]["values"]["ip"] == "10.0.0.50" and len(by_kind["duplicate_ip"]["values"]["macs"]) == 2

    # Filtri: priorità (i conteggi restano quelli di tutte le priorità), tipo, device anche come altro capo
    high = problems(client, severity="high")
    assert high["total"] == 7 and high["counts"]["medium"] == 5
    assert [p["kind"] for p in problems(client, kind="poe_budget")["items"]] == ["poe_budget", "poe_budget"]
    assert {p["kind"] for p in problems(client, device_id=b["id"])["items"]} >= {"native_vlan_mismatch", "duplex_mismatch"}


def test_hub_tra_due_switch(client, setup, session_factory):
    """Tre PC su un hub collegato alla Gi1/0/2 di sw-sim-01 e alla 2 di sw-sim-02: tutte e due vedono gli stessi MAC."""
    sw1, sw2 = copy.deepcopy(SW1), copy.deepcopy(SW2)
    sw1["fdb"] += [(None, mac, 2, 3) for mac in HUB]
    sw2["fdb"] += [(99, mac, 2, 3) for mac in HUB]
    sw1["arp"].append((99, "10.99.0.10", HUB[0]))  # un PC dell'hub ha l'IP di PC-A
    job_id = setup["job"]["id"]
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    approve_all(client)  # i device; il cavo tra i due arriva alla scansione dopo
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    found = {p["kind"]: p for p in problems(client)["items"]}
    link = found["undocumented_link"]
    assert link["severity"] == "medium" and link["values"] == {"macs": 3, "mac_list": HUB} and link["seen_at"]
    assert {(link["device_name"], link["interface_name"]), (link["other_device_name"], link["other_interface_name"])} == {
        ("sw-sim-01", "Gi1/0/2"), ("sw-sim-02", "2")}
    assert found["duplicate_ip"]["values"]["macs"] == sorted([PC_A_MAC, HUB[0]])

    # Con il cavo documentato tra i due switch l'hub è un secondo percorso: loop
    approve_all(client)
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    found = {p["kind"]: p for p in problems(client)["items"]}
    assert found["loop"]["severity"] == "critical" and "undocumented_link" not in found
    assert found["loop"]["values"]["mac_list"] == HUB

    # Hub tolto: alla scansione dopo il problema sparisce
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    assert "loop" not in {p["kind"] for p in problems(client)["items"]}
    assert device_named(client, "sw-sim-01")


def _verso(device: dict, lldp_num: int, port: str, neighbor: tuple) -> dict:
    """`device` con un vicino LLDP sulla porta `port` (numerazione LLDP `lldp_num`)."""
    device = copy.deepcopy(device)
    device["lldp_local"][lldp_num] = (5, port, port)
    device["lldp_remote"][(lldp_num, 1)] = neighbor
    return device


def test_trunk_verso_un_altro_switch_non_e_un_loop(client, setup, session_factory):
    """Gi1/0/2 di sw-sim-01 e 2 di sw-sim-02 sono trunk verso un core che NetMap non legge: vedono gli stessi MAC,
    ma il vicino LLDP si dichiara switch/router, quindi non è un hub né un loop."""
    core = (4, "00:AA:BB:CC:DD:00", 5, "Te1/0/1", "", "core-x.lab.local", None)
    sw1, sw2 = _verso(SW1, 2, "Gi1/0/2", core + (["bridge", "router"],)), _verso(SW2, 102, "2", core + (["bridge", "router"],))
    sw1["fdb"] += [(None, mac, 2, 3) for mac in HUB]
    sw2["fdb"] += [(99, mac, 2, 3) for mac in HUB]
    job_id = setup["job"]["id"]
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    approve_all(client)
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    assert not {"loop", "undocumented_link"} & {p["kind"] for p in problems(client)["items"]}

    # Un telefono fa anche da bridge, ma non è uno switch: dietro può esserci davvero un hub
    phone = core[:5] + ("phone-01", None, ["bridge", "telephone"])
    sw1, sw2 = _verso(SW1, 2, "Gi1/0/2", phone), _verso(SW2, 102, "2", phone)
    sw1["fdb"] += [(None, mac, 2, 3) for mac in HUB]
    sw2["fdb"] += [(99, mac, 2, 3) for mac in HUB]
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    assert "undocumented_link" in {p["kind"] for p in problems(client)["items"]}

    # Vicino senza capacità, ma è uno switch già in NetMap (letto da un'altra scansione): trunk anche così
    from app.models import Device, Site
    with session_factory() as db:
        db.add(Device(name="core-x", site_id=db.query(Site).first().id, sys_descr="HPE Comware Platform Software, 5130"))
        db.commit()
    sw1, sw2 = _verso(SW1, 2, "Gi1/0/2", core), _verso(SW2, 102, "2", core)
    sw1["fdb"] += [(None, mac, 2, 3) for mac in HUB]
    sw2["fdb"] += [(99, mac, 2, 3) for mac in HUB]
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    assert not {"loop", "undocumented_link"} & {p["kind"] for p in problems(client)["items"]}


def test_trunk_hp_non_e_un_loop(client, setup, session_factory):
    """sw-sim-02 arriva a sw-sim-01 con il Trk1 (porte 49 e 50): il vicino LLDP sta sulla 49, la tabella MAC sul Trk1.
    Senza sapere che la 49 fa parte del Trk1, i PC della Gi1/0/1 sembravano dietro due porte di accesso: un loop."""
    sw1, sw2 = copy.deepcopy(SW1), copy.deepcopy(SW2)
    sw1["fdb"] += [(None, mac, 1, 3) for mac in HUB]
    sw2["interfaces"][50] = ("50", "50", 6, 1500, 10000, "00:22:33:44:55:32", 1, 1, "")
    sw2["interfaces"][289] = ("Trk1", "Trk1", 54, 1500, 20000, "00:22:33:44:55:21", 1, 1, "")  # come l'E2910
    sw2["bridge_ports"] = {1: 1, 2: 2, 289: 289}
    sw2["pvid"] = {1: 99, 2: 99, 289: 1}
    sw2["fdb"] = [(vlan, mac, 289 if port == 49 else port, status) for vlan, mac, port, status in sw2["fdb"]]
    sw2["fdb"] += [(99, mac, 289, 3) for mac in HUB]
    job_id = setup["job"]["id"]

    # Come prima: membri del trunk non letti
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    approve_all(client)
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    assert {"loop", "undocumented_link"} & {p["kind"] for p in problems(client)["items"]}

    # Con i membri letti dalla ifStackTable: il Trk1 è un uplink, e le sue porte ne fanno parte da sole
    sw2["lag_members"] = {49: 289, 50: 289}
    scan(client, session_factory, job_id, (sw1, SW1_HOST), (sw2, SW2_HOST))
    assert not {"loop", "undocumented_link"} & {p["kind"] for p in problems(client)["items"]}
    assert [c["object_type"] for c in pending(client)] == ["cable"]  # i membri del Trk1 si legano da soli
    ports = ports_of(client, device_named(client, "sw-sim-02")["id"])
    assert ports["Trk1"]["type"] == "lag"
    assert ports["49"]["lag_id"] == ports["50"]["lag_id"] == ports["Trk1"]["id"]
    assert ports["1"]["lag_id"] is None


def test_uplink_non_riconosciuto_non_e_un_loop(client, setup, session_factory):
    """La Gi1/0/2 di sw-sim-01 è l'uplink verso il resto della rete, ma senza LLDP: vede i MAC delle porte di accesso
    di sw-sim-02 e di sw-sim-04 (tre PC per uno, dietro uno switchino). Non è un hub verso uno dei due: niente problemi,
    né sulla Gi1/0/2 né sulle porte di accesso degli altri due."""
    sw4 = copy.deepcopy(SW2)
    sw4["system"]["name"] = "sw-sim-04"
    sw4["entities"] = {1: (3, "SGSIM0004", "J9728A")}
    sw4["interfaces"] = {idx: (*row[:5], row[5].replace("00:22:33", "00:44:33"), *row[6:])
                         for idx, row in sw4["interfaces"].items()}
    sw4["ipv4"] = [("10.99.0.4", 1099, "255.255.255.0")]
    sw4["lldp_local"], sw4["lldp_remote"] = {}, {}
    far2 = ["00:50:56:00:02:01", "00:50:56:00:02:02", "00:50:56:00:02:03"]
    far4 = ["00:50:56:00:04:01", "00:50:56:00:04:02", "00:50:56:00:04:03"]
    sw1, sw2 = copy.deepcopy(SW1), copy.deepcopy(SW2)
    sw1["fdb"] += [(None, mac, 2, 3) for mac in far2 + far4]
    sw2["fdb"] += [(99, mac, 2, 3) for mac in far2]
    sw4["fdb"] = [(99, mac, 1, 3) for mac in far4]
    job_id = setup["job"]["id"]
    devices = (sw1, SW1_HOST), (sw2, SW2_HOST), (sw4, "10.99.0.4")
    scan(client, session_factory, job_id, *devices)
    approve_all(client)
    scan(client, session_factory, job_id, *devices)
    assert not {"loop", "undocumented_link"} & {p["kind"] for p in problems(client)["items"]}

    # Un hub vero tra sw-sim-02 e sw-sim-04 si vede ancora, anche se i suoi MAC passano dall'uplink di sw-sim-01
    sw1["fdb"] += [(None, mac, 2, 3) for mac in HUB]
    sw2["fdb"] += [(99, mac, 2, 3) for mac in HUB]
    sw4["fdb"] += [(99, mac, 2, 3) for mac in HUB]
    scan(client, session_factory, job_id, *devices)
    [link] = [p for p in problems(client)["items"] if p["kind"] == "undocumented_link"]
    assert {link["device_name"], link["other_device_name"]} == {"sw-sim-02", "sw-sim-04"}
    assert link["values"]["mac_list"] == HUB
