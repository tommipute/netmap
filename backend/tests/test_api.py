def create(client, path, payload):
    response = client.post(f"/api{path}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_cavi_vicini_e_topologia(client):
    site = create(client, "/sites", {"name": "Sede test"})
    sw1 = create(client, "/devices", {"name": "sw1", "site_id": site["id"]})
    sw2 = create(client, "/devices", {"name": "sw2", "site_id": site["id"]})
    a = create(client, "/interfaces", {"device_id": sw1["id"], "name": "Gi1/0/1", "mac_address": "aabb.ccdd.eeff"})
    b = create(client, "/interfaces", {"device_id": sw2["id"], "name": "Gi1/0/1"})
    c = create(client, "/interfaces", {"device_id": sw2["id"], "name": "Gi1/0/2"})
    assert a["mac_address"] == "AA:BB:CC:DD:EE:FF"

    create(client, "/cables", {"a_interface_id": a["id"], "b_interface_id": b["id"]})
    # 'a' ha già un cavo
    assert client.post("/api/cables", json={"a_interface_id": a["id"], "b_interface_id": c["id"]}).status_code == 422

    neighbors = client.get(f"/api/devices/{sw1['id']}/neighbors").json()
    assert neighbors[0]["remote_device"] == "sw2"
    assert neighbors[0]["remote_interface"] == "Gi1/0/1"

    topology = client.get("/api/topology", params={"site_id": site["id"]}).json()
    assert len(topology["nodes"]) == 2
    assert len(topology["edges"]) == 1

    found = client.get("/api/search", params={"q": "ccdd"}).json()
    assert any(r["type"] == "interface" and r["device_id"] == sw1["id"] for r in found)


def test_ipam(client):
    prefix = create(client, "/prefixes", {"prefix": "10.0.0.7/24"})
    assert prefix["prefix"] == "10.0.0.0/24"

    for address in ("10.0.0.10/24", "10.0.0.2/24", "10.0.0.1/24"):
        create(client, "/ip-addresses", {"address": address})
    assert client.post("/api/ip-addresses", json={"address": "10.0.0.2/24"}).status_code == 422

    # Ordinamento numerico, non alfabetico
    items = client.get("/api/ip-addresses").json()["items"]
    assert [ip["host"] for ip in items] == ["10.0.0.1", "10.0.0.2", "10.0.0.10"]

    usage = client.get(f"/api/prefixes/{prefix['id']}/utilization").json()
    assert usage["used"] == 3 and usage["total"] == 254

    free = client.get(f"/api/prefixes/{prefix['id']}/available-ips", params={"limit": 2}).json()
    assert free == ["10.0.0.3/24", "10.0.0.4/24"]


def test_vlan_tagged_solo_su_trunk(client):
    site = create(client, "/sites", {"name": "Sede"})
    dev = create(client, "/devices", {"name": "sw", "site_id": site["id"]})
    vlan = create(client, "/vlans", {"vid": 10, "name": "Uffici", "site_id": site["id"]})

    bad = {"device_id": dev["id"], "name": "1", "mode": "access", "tagged_vlan_ids": [vlan["id"]]}
    assert client.post("/api/interfaces", json=bad).status_code == 422

    trunk = create(client, "/interfaces", {**bad, "mode": "trunk"})
    assert trunk["tagged_vlan_ids"] == [vlan["id"]]

    updated = client.patch(f"/api/interfaces/{trunk['id']}", json={"mode": "access"}).json()
    assert updated["tagged_vlan_ids"] == []


def test_eliminazione_bloccata_se_in_uso(client):
    site = create(client, "/sites", {"name": "Sede"})
    dev = create(client, "/devices", {"name": "sw", "site_id": site["id"]})
    assert client.delete(f"/api/sites/{site['id']}").status_code == 409
    assert client.delete(f"/api/devices/{dev['id']}").status_code == 204
    assert client.delete(f"/api/sites/{site['id']}").status_code == 204


def test_filtri_e_riferimenti(client):
    s1 = create(client, "/sites", {"name": "Torino"})
    s2 = create(client, "/sites", {"name": "Milano"})
    create(client, "/devices", {"name": "core-to", "site_id": s1["id"]})
    create(client, "/devices", {"name": "core-mi", "site_id": s2["id"]})

    page = client.get("/api/devices", params={"site_id": s1["id"]}).json()
    assert page["total"] == 1 and page["items"][0]["name"] == "core-to"

    assert client.get("/api/devices", params={"q": "core"}).json()["total"] == 2
    assert client.post("/api/devices", json={"name": "x", "site_id": 999}).status_code == 422


def test_mappe_e_porte(client):
    site = create(client, "/sites", {"name": "Sede"})
    core = create(client, "/devices", {"name": "core", "site_id": site["id"]})
    sw = create(client, "/devices", {"name": "sw", "site_id": site["id"]})
    p10 = create(client, "/interfaces", {"device_id": core["id"], "name": "Gi1/0/10"})
    create(client, "/interfaces", {"device_id": core["id"], "name": "Gi1/0/2"})
    up = create(client, "/interfaces", {"device_id": sw["id"], "name": "49"})
    cable = create(client, "/cables", {"a_interface_id": p10["id"], "b_interface_id": up["id"], "type": "fiber_mm"})
    assert cable["a_device_name"] == "core" and cable["b_interface_name"] == "49"

    ports = client.get(f"/api/devices/{core['id']}/ports").json()
    assert [p["name"] for p in ports] == ["Gi1/0/2", "Gi1/0/10"]  # ordinamento naturale
    assert ports[1]["remote_device"] == "sw" and ports[0]["cable_id"] is None

    # Mappa automatica: tutti i device della sede, nessuna posizione salvata
    auto = create(client, "/maps", {"name": "Sede intera", "site_id": site["id"]})
    view = client.get(f"/api/maps/{auto['id']}/view").json()
    assert len(view["nodes"]) == 2 and len(view["edges"]) == 1
    assert all(n["x"] is None for n in view["nodes"])

    saved = client.put(f"/api/maps/{auto['id']}/nodes", json=[{"device_id": core["id"], "x": 10, "y": 20}])
    assert saved.json() == {"saved": 1}
    view = client.get(f"/api/maps/{auto['id']}/view").json()
    assert {n["name"]: n["x"] for n in view["nodes"]} == {"core": 10, "sw": None}

    # Mappa manuale: solo i device aggiunti
    manual = create(client, "/maps", {"name": "Solo core", "site_id": site["id"], "auto_include": False})
    view = client.get(f"/api/maps/{manual['id']}/view").json()
    client.put(f"/api/maps/{manual['id']}/nodes", json=[{"device_id": core["id"], "x": 0, "y": 0}])
    view = client.get(f"/api/maps/{manual['id']}/view").json()
    assert [n["name"] for n in view["nodes"]] == ["core"] and [a["name"] for a in view["available"]] == ["sw"]


def test_device_import_export(client):
    # Template
    tmpl = client.get("/api/devices/import/template")
    assert tmpl.status_code == 200
    assert "name" in tmpl.text

    # Import CSV
    csv_data = """name;status;site;location;rack;rack_position;manufacturer;model;role;primary_ip;serial;asset_tag;description
dev-imp-01;active;Sede Export;Sala 1;Rack 1;10;Cisco;C9300;Core;192.168.1.1/24;SN12345;AST-99;Dispositivo di test import
dev-imp-02;planned;Sede Export;Sala 1;Rack 1;12;HPE;2930;Switch;192.168.1.2/24;SN67890;AST-100;Secondo switch
"""
    res = client.post("/api/devices/import", json={"csv_data": csv_data, "update_existing": True, "dry_run": False})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["created_count"] == 2
    assert data["errors"] == []

    # Export CSV
    exp_csv = client.get("/api/devices/export", params={"format": "csv", "q": "dev-imp"})
    assert exp_csv.status_code == 200
    assert "dev-imp-01" in exp_csv.text
    assert "192.168.1.1/24" in exp_csv.text
    assert "Cisco" in exp_csv.text

    # Export JSON
    exp_json = client.get("/api/devices/export", params={"format": "json", "q": "dev-imp"}).json()
    assert len(exp_json) == 2
    assert exp_json[0]["name"] == "dev-imp-01"
    assert exp_json[0]["primary_ip"] == "192.168.1.1/24"
    assert exp_json[0]["site"] == "Sede Export"

