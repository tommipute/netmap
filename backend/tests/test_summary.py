"""Riepilogo "cosa è cambiato"."""
from datetime import datetime, timedelta, timezone

from app.models import Device, Endpoint
from tests.test_api import create


def test_cosa_e_cambiato(client, session_factory):
    site = create(client, "/sites", {"name": "Sede"})
    sw = create(client, "/devices", {"name": "sw-01", "site_id": site["id"]})
    port = create(client, "/interfaces", {"device_id": sw["id"], "name": "Gi0/1"})
    old_port = create(client, "/interfaces", {"device_id": sw["id"], "name": "Gi0/2"})
    gone = create(client, "/devices", {"name": "vecchio", "site_id": site["id"]})
    client.delete(f"/api/devices/{gone['id']}")
    client.patch(f"/api/devices/{sw['id']}", json={"description": "nota"})

    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.get(Device, sw["id"]).reachable = False
        db.get(Device, sw["id"]).reachable_changed_at = now - timedelta(minutes=5)
        db.add_all([
            Endpoint(mac="AA:00:00:00:00:01", interface_id=port["id"], first_seen_at=now, last_seen_at=now),
            Endpoint(mac="AA:00:00:00:00:02", interface_id=port["id"], previous_interface_id=old_port["id"],
                     moved_at=now, first_seen_at=now - timedelta(days=30), last_seen_at=now),
            Endpoint(mac="AA:00:00:00:00:03", interface_id=port["id"], first_seen_at=now - timedelta(days=30),
                     last_seen_at=now),
        ])
        db.commit()

    data = client.get("/api/whats-changed").json()
    assert data["changes"]["by_action"] == {"create": 6, "update": 1, "delete": 1}
    assert data["changes"]["by_source"] == {"utente": 7, "sistema": 1}  # sistema = l'admin creato da conftest
    assert [(d["name"], d["exists"]) for d in data["devices_created"]] == [("vecchio", False), ("sw-01", True)]
    assert [d["name"] for d in data["devices_deleted"]] == ["vecchio"]
    assert [(d["name"], d["new"]) for d in data["devices_down"]] == [("sw-01", True)]
    assert [e["mac"] for e in data["endpoints_new"]["items"]] == ["AA:00:00:00:00:01"]
    moved = data["endpoints_moved"]["items"]
    assert [(e["mac"], e["previous_interface_name"]) for e in moved] == [("AA:00:00:00:00:02", "Gi0/2")]

    # Da domani in poi: niente di nuovo, ma il device giù resta (non più "nuovo")
    later = client.get("/api/whats-changed", params={"since": (now + timedelta(days=1)).isoformat()}).json()
    assert later["changes"]["total"] == 0 and later["endpoints_new"]["total"] == 0
    assert [(d["name"], d["new"]) for d in later["devices_down"]] == [("sw-01", False)]


def test_panoramica(client, session_factory):
    site = create(client, "/sites", {"name": "Sede"})
    role = create(client, "/device-roles", {"name": "Switch", "color": "#00808a"})
    sw = create(client, "/devices", {"name": "sw-01", "site_id": site["id"], "role_id": role["id"],
                                     "management_ip": "10.0.0.2/24"})
    fw = create(client, "/devices", {"name": "fw-01", "site_id": site["id"]})
    a = create(client, "/interfaces", {"device_id": sw["id"], "name": "Gi0/1"})
    b = create(client, "/interfaces", {"device_id": fw["id"], "name": "port1"})
    create(client, "/cables", {"a_interface_id": a["id"], "b_interface_id": b["id"]})
    net = create(client, "/prefixes", {"prefix": "10.0.0.0/24"})
    create(client, "/prefixes", {"prefix": "10.9.0.0/30"})
    create(client, "/ip-addresses", {"address": "10.9.0.1/30"})
    with session_factory() as db:
        db.get(Device, sw["id"]).reachable = False
        db.commit()

    data = client.get("/api/dashboard").json()
    assert data["counts"]["devices"] == 2 and data["counts"]["cables"] == 1 and data["counts"]["prefixes"] == 2
    assert data["device_status"] == {"active": 2}
    assert data["live"]["down"] == 1 and [d["name"] for d in data["live"]["down_devices"]] == ["sw-01"]
    assert data["roles"] == [{"id": role["id"], "name": "Switch", "color": "#00808A", "count": 1},
                             {"id": None, "name": None, "color": None, "count": 1, "none": True}]
    assert data["sites"] == [{"id": site["id"], "name": "Sede", "count": 2, "down": 1}]
    assert data["ports"]["total"] == 3 and data["ports"]["cabled"] == 2  # anche la porta mgmt di sw-01
    # La /30 con un IP su due è più piena della /24 con uno su 254
    assert [(p["prefix"], p["used"], p["percent"]) for p in data["prefixes"]["items"]] == [
        ("10.9.0.0/30", 1, 50.0), ("10.0.0.0/24", 1, 0.4)]
    assert net["id"] == data["prefixes"]["items"][1]["id"]
    assert len(data["activity"]) == 14 and data["activity"][-1]["count"] > 0
    assert data["runs"]["last"] == [] and data["pending_changes"] == 0
    assert data["system"] is not None  # admin
