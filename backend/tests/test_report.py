"""Report (porte più cariche, errori, porte libere, PoE, disponibilità) e problemi silenziati."""
from datetime import datetime, timedelta, timezone

from app.services import port_stats, reports
from app.services.monitor import Probe, check_devices
from tests.test_discovery import create
from tests.test_porte_dettagli import device_with_ports, set_if_index
from tests.test_problemi import problems


def test_percentile():
    assert reports.percentile([]) is None
    assert reports.percentile([5]) == 5
    values = list(range(1, 101))  # 1..100: il 95° è 95, i 5 punti più alti non contano
    assert reports.percentile(values) == 95
    assert reports.percentile([1] * 19 + [1000]) == 1  # un picco su 20 punti (5%) non sposta il 95°


def test_report_delle_porte(client, session_factory):
    from app.models import Device, Interface
    device, ports = device_with_ports(client)
    other = create(client, "/devices", {"name": "sw-altro", "site_id": device["site_id"]})
    far = create(client, "/interfaces", {"device_id": other["id"], "name": "49"})
    create(client, "/cables", {"a_interface_id": ports["Gi1/0/1"]["id"], "b_interface_id": far["id"]})
    first, second, third = (ports[n]["id"] for n in ("Gi1/0/1", "Gi1/0/2", "Gi1/0/3"))
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        for iface_id, speed in ((first, 100), (second, 1000), (third, 1000)):
            db.get(Interface, iface_id).speed_mbps = speed
        # Gi1/0/1 a 100 Mbit/s: 20 intervalli da 5 minuti, 19 a 90 Mbit/s e uno a 100 → satura
        for i in range(20):
            bps = 100_000_000 if i == 0 else 90_000_000
            sample = port_stats.Sample(first, 300, in_octets=bps * 300 // 8, out_octets=1000, up=True, errors=3 if i == 5 else 0)
            port_stats.record(db, [sample], now - timedelta(minutes=5 * i + 1))
        # Gi1/0/2: poco traffico e un picco; Gi1/0/3: contatori fermi
        for i in range(20):
            port_stats.record(db, [port_stats.Sample(second, 300, in_octets=(10**9 if i == 3 else 10**6), out_octets=0, up=True),
                                   port_stats.Sample(third, 300, in_octets=0, out_octets=0, up=False, discards=1)],
                              now - timedelta(minutes=5 * i + 1))
        dev = db.get(Device, device["id"])
        dev.poe_budget_w, dev.poe_used_w = 370, 300
        db.get(Interface, first).poe_status = "delivering"
        db.get(Interface, second).poe_status = "fault"
        db.get(Interface, first).oper_status = "up"
        db.get(Interface, second).oper_status, db.get(Interface, second).oper_changed_at = "down", now - timedelta(days=40)
        db.get(Interface, third).oper_status, db.get(Interface, third).oper_changed_at = "down", now - timedelta(days=3)
        db.commit()

    usage = client.get("/api/reports/port-usage", params={"range": "1d"}).json()
    assert [i["interface_name"] for i in usage["items"]] == ["Gi1/0/1", "Gi1/0/2"]  # la 3 non ha traffico
    top = usage["items"][0]
    assert top["in_p95_bps"] == 90_000_000 and top["in_peak_bps"] == 100_000_000 and top["usage"] == 0.9
    assert top["saturated"] and usage["saturated"] == 1
    assert (top["remote_device"], top["remote_interface"]) == ("sw-altro", "49")
    assert usage["items"][1]["in_p95_bps"] < usage["items"][1]["in_peak_bps"]  # il picco non conta nel 95°
    cabled = client.get("/api/reports/port-usage", params={"range": "1d", "cabled": True}).json()
    assert [i["interface_name"] for i in cabled["items"]] == ["Gi1/0/1"]
    assert client.get("/api/reports/port-usage", params={"site_id": 999999}).json()["total"] == 0
    assert client.get("/api/reports/port-usage", params={"range": "1y"}).status_code == 422

    errors = client.get("/api/reports/port-errors", params={"range": "1d"}).json()
    assert [(i["interface_name"], i["errors"], i["discards"]) for i in errors["items"]] == [("Gi1/0/1", 3, 0), ("Gi1/0/3", 0, 20)]

    free = client.get("/api/reports/free-ports", params={"days": 30}).json()
    row = next(i for i in free["items"] if i["device_name"] == "sw-poe")
    assert (row["ports"], row["up"], row["down"], row["free"], row["free_ports"]) == (3, 1, 2, 1, ["Gi1/0/2"])
    assert client.get("/api/reports/free-ports", params={"days": 2}).json()["free"] == 2

    poe = client.get("/api/reports/poe").json()
    assert poe["items"][0]["usage"] == round(300 / 370, 4)
    assert (poe["items"][0]["delivering"], poe["items"][0]["fault"]) == (1, 1)


def test_disponibilita(client, session_factory):
    device, _ = device_with_ports(client)
    reachable = {"value": True}

    def probe(targets):
        return {device["id"]: Probe(reachable=reachable["value"], rtt_ms=2.0 if reachable["value"] else None)}

    for state in (True, True, True, False):
        reachable["value"] = state
        with session_factory() as db:
            check_devices(db, prober=probe)
    data = client.get("/api/reports/availability", params={"range": "7d"}).json()
    row = next(i for i in data["items"] if i["device_name"] == "sw-poe")
    assert (row["checks"], row["failed"], row["availability"], row["rtt_ms"]) == (4, 1, 0.75, 2.0)
    assert row["reachable"] is False

    from app.models import DeviceStat
    from app.services import device_stats
    with session_factory() as db:
        assert {r.period for r in db.query(DeviceStat)} == {"1h", "1d"}
        assert device_stats.prune(db, datetime.now(timezone.utc) + timedelta(days=31)) == 1  # l'ora; il giorno resta


def test_problemi_silenziati(client, session_factory):
    from app.models import Interface
    device, ports = device_with_ports(client)
    set_if_index(session_factory, ports)
    with session_factory() as db:
        db.get(Interface, ports["Gi1/0/1"]["id"]).err_disabled = "bpduGuard"
        db.get(Interface, ports["Gi1/0/2"]["id"]).poe_status = "fault"
        db.commit()
    found = problems(client)
    assert found["total"] == 2 and found["silenced"] == []
    key = next(p["key"] for p in found["items"] if p["kind"] == "err_disabled")
    assert key == f"err_disabled:{device['id']}:{ports['Gi1/0/1']['id']}"

    silence = client.post("/api/problems/silences", json={"key": key, "note": " voluto ", "days": 7})
    assert silence.status_code == 201
    assert silence.json()["note"] == "voluto" and silence.json()["until"]
    found = problems(client)
    assert found["total"] == 1 and found["counts"]["high"] == 1
    assert [p["kind"] for p in found["silenced"]] == ["err_disabled"]
    assert found["silenced"][0]["silenced"]["note"] == "voluto"
    # nella scheda del device e in Panoramica non conta
    assert problems(client, device_id=device["id"])["total"] == 1
    # silenziare di nuovo cambia solo nota e scadenza
    again = client.post("/api/problems/silences", json={"key": key}).json()
    assert again["id"] == silence.json()["id"] and again["until"] is None and again["note"] is None

    assert client.post("/api/problems/silences", json={"key": "loop:1:2"}).status_code == 404
    assert client.delete(f"/api/problems/silences/{again['id']}").status_code == 204
    assert problems(client)["total"] == 2
    assert client.delete(f"/api/problems/silences/{again['id']}").status_code == 404

    # Scaduto: il problema torna
    from app.models import ProblemSilence
    client.post("/api/problems/silences", json={"key": key, "days": 1})
    with session_factory() as db:
        db.query(ProblemSilence).one().until = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert problems(client)["total"] == 2
