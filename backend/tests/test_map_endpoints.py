"""Endpoint (tabelle MAC) nella vista della mappa."""
from datetime import datetime, timezone

from app.models import Endpoint
from tests.test_api import create


def test_endpoint_nella_vista_della_mappa(client, session_factory):
    site = create(client, "/sites", {"name": "Sede"})
    core = create(client, "/devices", {"name": "core", "site_id": site["id"]})
    sw = create(client, "/devices", {"name": "sw", "site_id": site["id"]})
    altrove = create(client, "/devices", {"name": "altrove", "site_id": site["id"]})
    p1 = create(client, "/interfaces", {"device_id": core["id"], "name": "Gi1/0/1"})
    p2 = create(client, "/interfaces", {"device_id": core["id"], "name": "Gi1/0/2"})
    up = create(client, "/interfaces", {"device_id": sw["id"], "name": "49"})
    other = create(client, "/interfaces", {"device_id": altrove["id"], "name": "1"})
    create(client, "/ip-addresses", {"address": "10.0.0.2/24", "interface_id": up["id"]})

    now = datetime.now(timezone.utc)
    with session_factory() as db:
        db.add_all([
            Endpoint(mac="AA:00:00:00:00:01", ip="10.0.0.50", vlan=10, interface_id=p1["id"], macs_on_port=1,
                     first_seen_at=now, last_seen_at=now),
            # È "sw": con sw in mappa non serve una seconda volta
            Endpoint(mac="AA:00:00:00:00:02", ip="10.0.0.2", interface_id=p2["id"], first_seen_at=now, last_seen_at=now),
            # Su un device fuori dalla mappa manuale
            Endpoint(mac="AA:00:00:00:00:03", interface_id=other["id"], first_seen_at=now, last_seen_at=now),
        ])
        db.commit()

    manual = create(client, "/maps", {"name": "Core e sw", "site_id": site["id"], "auto_include": False})
    client.put(f"/api/maps/{manual['id']}/nodes", json=[{"device_id": core["id"], "x": 0, "y": 0},
                                                        {"device_id": sw["id"], "x": 0, "y": 200}])
    view = client.get(f"/api/maps/{manual['id']}/view").json()
    assert view["endpoint_total"] == 1
    [e] = view["endpoints"]
    assert (e["mac"], e["ip"], e["vlan"], e["device_id"], e["interface_name"]) == (
        "AA:00:00:00:00:01", "10.0.0.50", 10, core["id"], "Gi1/0/1")

    # Senza sw in mappa, il suo endpoint compare con il nome del device che lo conosce
    client.put(f"/api/maps/{manual['id']}/nodes", json=[{"device_id": core["id"], "x": 0, "y": 0}])
    view = client.get(f"/api/maps/{manual['id']}/view").json()
    assert [(e["mac"], e["known_as"], e["known_device_id"]) for e in view["endpoints"]] == [
        ("AA:00:00:00:00:01", None, None), ("AA:00:00:00:00:02", "sw 49", sw["id"])]

    # Mappa vuota: niente endpoint
    empty = create(client, "/maps", {"name": "Vuota", "site_id": site["id"], "auto_include": False})
    view = client.get(f"/api/maps/{empty['id']}/view").json()
    assert view["endpoints"] == [] and view["endpoint_total"] == 0
