"""Stack: un solo device, con i singoli switch come membri."""
from tests.test_api import create
from tests.test_discovery import SW1, SW1_HOST, approve_all, device_named, pending, scan, setup  # noqa: F401


def members(client, device_id):
    return client.get("/api/stack-members", params={"device_id": device_id}).json()["items"]


def test_membri_dalla_scansione(client, setup, session_factory):
    job_id = setup["job"]["id"]
    scan(client, session_factory, job_id, (SW1, SW1_HOST))
    new = next(c for c in pending(client) if c["object_type"] == "device")
    assert new["diff"] and ["Stack", None, "2 switch"] in new["diff"]
    approve_all(client)
    device = device_named(client, "sw-sim-01")
    found = members(client, device["id"])
    assert [(m["number"], m["serial"], m["source"]) for m in found] == [(1, "FOCSIM0001", "snmp"), (2, "FOCSIM0003", "snmp")]

    # Un membro aggiunto a mano che lo switch non mostra: si propone di toglierlo, non sparisce da solo
    extra = create(client, "/stack-members", {"device_id": device["id"], "number": 3, "serial": "MANO3"})
    scan(client, session_factory, job_id, (SW1, SW1_HOST))
    stale = [c for c in pending(client) if c["object_type"] == "stack_member"]
    assert [(c["action"], c["object_id"]) for c in stale] == [("stale", extra["id"])]

    # Ricerca per seriale di un membro: porta al device dello stack
    results = client.get("/api/search", params={"q": "FOCSIM0003"}).json()
    assert any(r["type"] == "device" and r["device_id"] == device["id"] and "membro 2" in r["detail"] for r in results)

    # Nello storico, con il nome del device
    history = client.get("/api/audit-log", params={"object_type": "stack_member"}).json()["items"]
    assert {h["label"] for h in history} >= {"sw-sim-01 membro 1", "sw-sim-01 membro 3"}


def test_stack_nel_rack_e_in_mappa(client):
    site = create(client, "/sites", {"name": "Sede"})
    rack = create(client, "/racks", {"name": "R1", "site_id": site["id"], "u_height": 42})
    loose = create(client, "/devices", {"name": "senza-rack", "site_id": site["id"]})
    assert client.post("/api/stack-members", json={"device_id": loose["id"], "number": 1, "rack_position": 5}).status_code == 422

    stack = create(client, "/devices", {"name": "stack", "site_id": site["id"], "rack_id": rack["id"], "rack_position": 10})
    create(client, "/stack-members", {"device_id": stack["id"], "number": 1, "serial": "A", "rack_position": 10})
    create(client, "/stack-members", {"device_id": stack["id"], "number": 2, "serial": "B", "rack_position": 12})
    duplicate = client.post("/api/stack-members", json={"device_id": stack["id"], "number": 2})
    assert duplicate.status_code == 422 and "numero 2" in duplicate.json()["detail"]

    view = client.get(f"/api/racks/{rack['id']}/elevation").json()
    assert [(d["name"], d["member"], d["position"]) for d in view["devices"]] == [("stack", 1, 10), ("stack", 2, 12)]
    assert all(d["member_id"] for d in view["devices"])
    assert view["used_units"] == 2

    the_map = create(client, "/maps", {"name": "Sede", "site_id": site["id"]})
    nodes = {n["name"]: n["stack_size"] for n in client.get(f"/api/maps/{the_map['id']}/view").json()["nodes"]}
    assert nodes == {"stack": 2, "senza-rack": 0}

    # Lo stack esce dal rack: le unità dei membri si svuotano
    client.patch(f"/api/devices/{stack['id']}", json={"rack_id": None, "rack_position": None})
    assert [m["rack_position"] for m in client.get("/api/stack-members", params={"device_id": stack["id"]}).json()["items"]] == [None, None]

    # Eliminato il device, spariscono anche i membri
    client.delete(f"/api/devices/{stack['id']}")
    assert client.get("/api/stack-members").json()["total"] == 0
