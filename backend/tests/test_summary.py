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
