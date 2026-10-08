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
    create(client, "/interfaces", {"device_id": core["id"], "name": "mgmt"})
    create(client, "/interfaces", {"device_id": core["id"], "name": "Gi0/0", "mgmt_only": True})
    ports = client.get(f"/api/devices/{core['id']}/ports").json()
    assert [p["name"] for p in ports] == ["Gi0/0", "mgmt", "Gi1/0/2", "Gi1/0/10"]  # management in cima
    assert ports[3]["remote_device"] == "sw" and ports[3]["remote_interface"] == "49" and ports[2]["cable_id"] is None

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


def test_patch_valida_e_modifica_solo_i_campi_inviati(client):
    site = create(client, "/sites", {"name": "Sede"})
    dev = create(client, "/devices", {"name": "sw", "site_id": site["id"], "serial": "SN1", "status": "planned"})
    port = create(client, "/interfaces", {"device_id": dev["id"], "name": "1", "mac_address": "aa:bb:cc:dd:ee:ff"})

    # Le validazioni dello schema valgono anche nel PATCH
    assert client.patch(f"/api/interfaces/{port['id']}", json={"mac_address": "non-un-mac"}).status_code == 422
    assert client.patch(f"/api/devices/{dev['id']}", json={"name": "   "}).status_code == 422
    assert client.patch(f"/api/devices/{dev['id']}", json={"rack_position": 99}).status_code == 422
    assert client.patch(f"/api/devices/{dev['id']}", json={"campo_inventato": 1}).status_code == 422

    # Un solo campo: gli altri restano com'erano
    updated = client.patch(f"/api/devices/{dev['id']}", json={"description": "nota"}).json()
    assert updated["description"] == "nota"
    assert updated["serial"] == "SN1" and updated["status"] == "planned" and updated["name"] == "sw"
    mac = client.patch(f"/api/interfaces/{port['id']}", json={"mac_address": "1122.3344.5566"}).json()["mac_address"]
    assert mac == "11:22:33:44:55:66"


def test_seed_di_esempio(client, session_factory):
    from app.seed import load_demo

    for expected in (True, False):  # la seconda volta non carica doppioni
        with session_factory() as db:
            assert load_demo(db) is expected

    counts = {path: client.get(f"/api/{path}").json()["total"] for path in ("devices", "cables", "vlans", "prefixes", "maps")}
    assert counts == {"devices": 4, "cables": 3, "vlans": 3, "prefixes": 3, "maps": 1}

    map_id = client.get("/api/maps").json()["items"][0]["id"]
    view = client.get(f"/api/maps/{map_id}/view").json()
    assert len(view["nodes"]) == 4 and len(view["edges"]) == 3
    # Nessuna posizione salvata: la disposizione automatica parte nel browser, per livello del ruolo
    assert all(n["x"] is None for n in view["nodes"])
    assert sorted(n["level"] for n in view["nodes"]) == [0, 1, 2, 2]


def test_mappa_con_vlan_e_ricerca_della_porta(client):
    site = create(client, "/sites", {"name": "Sede"})
    v10 = create(client, "/vlans", {"vid": 10, "name": "Uffici", "site_id": site["id"]})
    v20 = create(client, "/vlans", {"vid": 20, "name": "Voce", "site_id": site["id"]})
    v30 = create(client, "/vlans", {"vid": 30, "name": "Ospiti", "site_id": site["id"]})
    core = create(client, "/devices", {"name": "core", "site_id": site["id"]})
    sw = create(client, "/devices", {"name": "sw", "site_id": site["id"]})
    srv = create(client, "/devices", {"name": "srv", "site_id": site["id"]})
    trunk_core = create(client, "/interfaces", {"device_id": core["id"], "name": "Te1/1", "mode": "trunk",
                                                "tagged_vlan_ids": [v10["id"], v20["id"], v30["id"]]})
    trunk_sw = create(client, "/interfaces", {"device_id": sw["id"], "name": "Te0/1", "mode": "trunk",
                                              "tagged_vlan_ids": [v10["id"], v20["id"]]})
    access = create(client, "/interfaces", {"device_id": sw["id"], "name": "Gi0/5", "mode": "access",
                                            "untagged_vlan_id": v10["id"], "mac_address": "aa:bb:cc:00:11:22"})
    nic = create(client, "/interfaces", {"device_id": srv["id"], "name": "eth0"})
    create(client, "/cables", {"a_interface_id": trunk_core["id"], "b_interface_id": trunk_sw["id"]})
    create(client, "/cables", {"a_interface_id": access["id"], "b_interface_id": nic["id"]})

    the_map = create(client, "/maps", {"name": "Sede", "site_id": site["id"]})
    view = client.get(f"/api/maps/{the_map['id']}/view").json()
    assert [v["vid"] for v in view["vlans"]] == [10, 20, 30]
    nodes = {n["name"]: n["vlan_ids"] for n in view["nodes"]}
    assert nodes == {"core": [v10["id"], v20["id"], v30["id"]], "sw": [v10["id"], v20["id"]], "srv": []}
    edges = {(e["source_interface"], e["target_interface"]): e for e in view["edges"]}
    # Documentate da tutti e due i lati: solo quelle in comune; da un lato solo: quelle
    assert edges[("Te1/1", "Te0/1")]["vlan_ids"] == [v10["id"], v20["id"]]
    assert edges[("Gi0/5", "eth0")]["vlan_ids"] == [v10["id"]]
    assert edges[("Gi0/5", "eth0")]["source_interface_id"] == access["id"]

    found = client.get("/api/search", params={"q": "aa:bb:cc:00"}).json()
    assert {"type": "interface", "device_id": sw["id"], "interface_id": access["id"]}.items() <= found[0].items()


def test_punti_di_ancoraggio_dei_cavi(client):
    site = create(client, "/sites", {"name": "Sede"})
    other = create(client, "/sites", {"name": "Altra"})
    a = create(client, "/devices", {"name": "a", "site_id": site["id"]})
    b = create(client, "/devices", {"name": "b", "site_id": site["id"]})
    x = create(client, "/devices", {"name": "x", "site_id": other["id"]})
    y = create(client, "/devices", {"name": "y", "site_id": other["id"]})
    pa, pb = (create(client, "/interfaces", {"device_id": d["id"], "name": "1"}) for d in (a, b))
    px, py = (create(client, "/interfaces", {"device_id": d["id"], "name": "1"}) for d in (x, y))
    cable = create(client, "/cables", {"a_interface_id": pa["id"], "b_interface_id": pb["id"]})
    foreign = create(client, "/cables", {"a_interface_id": px["id"], "b_interface_id": py["id"]})
    the_map = create(client, "/maps", {"name": "Sede", "site_id": site["id"]})
    url = f"/api/maps/{the_map['id']}/routes"

    points = [{"x": 10, "y": 20.04}, {"x": 300, "y": 20}]
    assert client.put(url, json=[{"cable_id": cable["id"], "points": points}]).json() == {"saved": 1}
    view = client.get(f"/api/maps/{the_map['id']}/view").json()
    assert view["routes"] == [{"cable_id": cable["id"], "points": [{"x": 10, "y": 20.0}, {"x": 300, "y": 20}],
                               "a_end": None, "b_end": None}]

    # Solo un'estremità spostata: il percorso resta automatico ma il cavo si attacca lì
    end = {"side": "right", "f": 0.25}
    assert client.put(url, json=[{"cable_id": cable["id"], "a_end": end}]).json() == {"saved": 1}
    route = client.get(f"/api/maps/{the_map['id']}/view").json()["routes"][0]
    assert route["points"] == [] and route["a_end"] == end and route["b_end"] is None
    assert client.put(url, json=[{"cable_id": cable["id"], "a_end": {"side": "fuori", "f": 2}}]).status_code == 422

    assert client.put(url, json=[{"cable_id": foreign["id"], "points": points}]).status_code == 422
    # Senza punti: il cavo torna al percorso automatico
    assert client.put(url, json=[{"cable_id": cable["id"], "points": []}]).json() == {"saved": 0}
    assert client.get(f"/api/maps/{the_map['id']}/view").json()["routes"] == []
    # Eliminato il cavo, spariscono anche i suoi punti
    client.put(url, json=[{"cable_id": cable["id"], "points": points}])
    client.delete(f"/api/cables/{cable['id']}")
    assert client.get(f"/api/maps/{the_map['id']}/view").json()["routes"] == []


def test_filtri_per_colonna_e_ordinamento(client):
    site = create(client, "/sites", {"name": "Sede"})
    rack = create(client, "/racks", {"name": "R1", "site_id": site["id"]})
    create(client, "/devices", {"name": "sw-piano-1", "site_id": site["id"], "rack_id": rack["id"], "serial": "ABC123"})
    create(client, "/devices", {"name": "sw-piano-2", "site_id": site["id"], "status": "planned"})
    create(client, "/devices", {"name": "fw", "site_id": site["id"], "management_ip": "10.0.0.1/24"})

    def names(**params):
        return [d["name"] for d in client.get("/api/devices", params=params).json()["items"]]

    assert names(name__contains="PIANO") == ["sw-piano-1", "sw-piano-2"]  # senza maiuscole
    assert names(rack_id__eq=rack["id"]) == ["sw-piano-1"]
    assert names(rack_id__isnull="true") == ["fw", "sw-piano-2"]
    assert names(status__eq="planned") == ["sw-piano-2"]
    assert names(serial__contains="c12") == ["sw-piano-1"]
    assert names(management_ip__contains="10.0.0") == ["fw"]  # campo calcolato
    assert names(name__contains="sw", sort="-name") == ["sw-piano-2", "sw-piano-1"]
    assert client.get("/api/devices", params={"inventato__contains": "x"}).status_code == 422
    assert client.get("/api/devices", params={"rack_id__eq": "abc"}).status_code == 422
    assert client.get("/api/devices", params={"sort": "inventato"}).status_code == 422


def test_export_con_i_filtri_per_colonna(client):
    site = create(client, "/sites", {"name": "Sede"})
    create(client, "/devices", {"name": "sw-a", "site_id": site["id"]})
    create(client, "/devices", {"name": "fw-b", "site_id": site["id"]})
    rows = client.get("/api/devices/export", params={"format": "json", "name__contains": "SW"}).json()
    assert [r["name"] for r in rows] == ["sw-a"]


def test_posizioni_ad_albero(client):
    site = create(client, "/sites", {"name": "Grugliasco"})
    a = create(client, "/locations", {"name": "Palazzina A", "site_id": site["id"]})
    create(client, "/locations", {"name": "Palazzina AB", "site_id": site["id"]})
    p1 = create(client, "/locations", {"name": "P1", "site_id": site["id"], "parent_id": a["id"]})
    stanza = create(client, "/locations", {"name": "Stanza 3", "site_id": site["id"], "parent_id": p1["id"]})
    assert stanza["path"] == "Palazzina A › P1 › Stanza 3"

    # Ordine predefinito = albero: le posizioni contenute subito sotto la loro, prima di "Palazzina AB"
    items = client.get("/api/locations", params={"site_id": site["id"]}).json()["items"]
    assert [i["path"] for i in items] == [
        "Palazzina A", "Palazzina A › P1", "Palazzina A › P1 › Stanza 3", "Palazzina AB",
    ]
    assert client.get("/api/locations", params={"q": "palazzina a › p1"}).json()["total"] == 2

    # Rinominare o spostare una posizione aggiorna anche quelle che contiene
    client.patch(f"/api/locations/{a['id']}", json={"name": "Edificio A"})
    assert client.get(f"/api/locations/{stanza['id']}").json()["path"] == "Edificio A › P1 › Stanza 3"
    client.patch(f"/api/locations/{p1['id']}", json={"parent_id": None})
    assert client.get(f"/api/locations/{stanza['id']}").json()["path"] == "P1 › Stanza 3"

    # Stesso nome allo stesso livello: rifiutato anche al livello principale (lì il vincolo unico non basta)
    doppia = client.post("/api/locations", json={"name": "P1", "site_id": site["id"]})
    assert doppia.status_code == 422
    assert client.post("/api/locations", json={"name": "P1", "site_id": site["id"], "parent_id": a["id"]}).status_code == 201
    circolare = client.patch(f"/api/locations/{p1['id']}", json={"parent_id": stanza["id"]})
    assert circolare.status_code == 422


def test_mappa_con_le_posizioni(client):
    site = create(client, "/sites", {"name": "Sede bolle"})
    pal = create(client, "/locations", {"name": "Palazzina A", "site_id": site["id"]})
    piano = create(client, "/locations", {"name": "P1", "site_id": site["id"], "parent_id": pal["id"], "floor": 1})
    create(client, "/locations", {"name": "Vuota", "site_id": site["id"]})
    create(client, "/devices", {"name": "sw-p1", "site_id": site["id"], "location_id": piano["id"]})
    mappa = create(client, "/maps", {"name": "Bolle", "site_id": site["id"], "auto_include": True})
    view = client.get(f"/api/maps/{mappa['id']}/view").json()
    # Solo le posizioni con device in mappa, più quelle che le contengono (per le bolle una dentro l'altra)
    assert [(l["name"], l["parent_id"], l["floor"]) for l in view["locations"]] == [
        ("Palazzina A", None, None), ("P1", pal["id"], 1),
    ]
