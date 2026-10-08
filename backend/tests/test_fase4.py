"""Fase 4: dov'è collegato (tabelle MAC e ARP), stato live, login e permessi, vista del rack."""
import copy

import pytest
from starlette.requests import Request

from app.config import settings
from app.core.throttle import Throttle, client_ip
from app.services.monitor import Probe, check_devices
from tests.conftest import ADMIN
from tests.snmp_devices import PC_A_MAC, PC_B_MAC, SW1, SW2
from tests.test_discovery import SW1_HOST, SW2_HOST, approve_all, create, device_named, ports_of, scan, setup  # noqa: F401


# ---------------------------------------------------------------- dov'è collegato
def endpoints(client, **params):
    return {e["mac"]: e for e in client.get("/api/endpoints", params=params).json()["items"]}


def test_endpoint_sulla_porta_di_accesso_non_sugli_uplink(client, setup, session_factory):
    job_id = setup["job"]["id"]
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    assert endpoints(client) == {}  # device non ancora approvati: le loro tabelle non si usano
    approve_all(client)

    # Il cavo tra i due switch non è ancora approvato: gli uplink si riconoscono dai vicini LLDP
    result = scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    assert "2 endpoint localizzati" in result["log"]
    found = endpoints(client)
    assert set(found) == {PC_A_MAC, PC_B_MAC}  # i MAC degli switch visti sugli uplink non compaiono
    a, b = found[PC_A_MAC], found[PC_B_MAC]
    assert (a["device_name"], a["interface_name"], a["ip"], a["vlan"]) == ("sw-sim-01", "Gi1/0/1", "10.99.0.10", None)
    assert (b["device_name"], b["interface_name"], b["ip"], b["vlan"]) == ("sw-sim-02", "1", "10.99.0.20", 99)
    assert b["site"] == "Laboratorio" and b["macs_on_port"] == 1

    # Con il cavo approvato il risultato non cambia
    approve_all(client)
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    assert endpoints(client)[PC_B_MAC]["interface_name"] == "1"

    # Ricerca per IP, MAC in formato Cisco e per switch
    assert list(endpoints(client, q="10.99.0.20")) == [PC_B_MAC]
    assert list(endpoints(client, q="0050.5600.0010")) == [PC_A_MAC]
    sw2 = device_named(client, "sw-sim-02")
    assert list(endpoints(client, device_id=sw2["id"])) == [PC_B_MAC]
    assert ports_of(client, sw2["id"])["1"]["endpoints"] == 1
    results = client.get("/api/search", params={"q": "10.99.0.20"}).json()
    assert [r["detail"] for r in results if r["type"] == "endpoint"] == ["sw-sim-02 1"]

    # Il PC-A si sposta su Gi1/0/2: si ricorda da dove viene
    moved = copy.deepcopy(SW1)
    moved["fdb"][0] = (None, PC_A_MAC, 2, 3)
    scan(client, session_factory, job_id, (moved, SW1_HOST), (SW2, SW2_HOST))
    a = endpoints(client)[PC_A_MAC]
    assert (a["interface_name"], a["previous_interface_name"], a["previous_device_name"]) == ("Gi1/0/2", "Gi1/0/1", "sw-sim-01")
    assert a["moved_at"] is not None


def test_endpoint_riconosciuto_dalla_documentazione(client, setup, session_factory):
    job_id = setup["job"]["id"]
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    approve_all(client)
    create(client, "/ip-addresses", {"address": "10.99.0.20/24", "dns_name": "pc-contabilita.lab.local"})
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    found = endpoints(client, q="contabilita")
    assert list(found) == [PC_B_MAC] and found[PC_B_MAC]["known_as"] == "pc-contabilita.lab.local"


# ---------------------------------------------------------------- stato live
@pytest.fixture()
def monitored(client):
    site = create(client, "/sites", {"name": "Sede"})
    devices = {}
    for name, status, ip in (("fw", "active", "10.0.0.1/24"), ("sw", "active", "10.0.0.2/24"),
                             ("nuovo", "planned", "10.0.0.3/24"), ("senza-ip", "active", None)):
        device = create(client, "/devices", {"name": name, "site_id": site["id"], "status": status})
        port = create(client, "/interfaces", {"device_id": device["id"], "name": "mgmt0"})
        if ip:
            create(client, "/ip-addresses", {"address": ip, "interface_id": port["id"], "is_primary": True})
        devices[name] = {**device, "port": port}
    return {"site": site, "devices": devices}


def test_monitor_aggiorna_stato_e_porte(client, monitored, session_factory):
    fw, sw = monitored["devices"]["fw"], monitored["devices"]["sw"]
    with session_factory() as db:
        from app.models import Interface
        db.get(Interface, sw["port"]["id"]).if_index = 7
        db.commit()

    seen = []

    def prober(targets):
        seen.extend(t.host for t in targets)
        return {fw["id"]: Probe(reachable=True, rtt_ms=1.234), sw["id"]: Probe(reachable=False, oper_status={7: "down"})}

    with session_factory() as db:
        assert check_devices(db, prober=prober) == {"checked": 2, "up": 1, "down": 1}
    assert sorted(seen) == ["10.0.0.1", "10.0.0.2"]  # niente device pianificati o senza IP

    device = client.get(f"/api/devices/{fw['id']}").json()
    assert device["reachable"] is True and device["rtt_ms"] == 1.23 and device["last_check_at"]
    assert client.get(f"/api/devices/{sw['id']}").json()["reachable"] is False
    assert ports_of(client, sw["id"])["mgmt0"]["oper_status"] == "down"
    summary = client.get("/api/status/summary").json()
    assert (summary["up"], summary["down"], summary["unknown"]) == (1, 1, 1)  # senza-ip: mai controllato
    # Filtro usato dal riepilogo in alto ("N non rispondono")
    down = client.get("/api/devices?reachable=false").json()
    assert [d["name"] for d in down["items"]] == ["sw"]

    the_map = create(client, "/maps", {"name": "Sede", "site_id": monitored["site"]["id"]})
    nodes = {n["name"]: n for n in client.get(f"/api/maps/{the_map['id']}/view").json()["nodes"]}
    assert nodes["fw"]["reachable"] is True and nodes["sw"]["reachable"] is False and nodes["nuovo"]["reachable"] is None

    # Il cambio di stato si registra solo quando cambia davvero
    with session_factory() as db:
        check_devices(db, prober=prober)
    again = client.get(f"/api/devices/{fw['id']}").json()
    assert again["reachable_changed_at"] == device["reachable_changed_at"]


def test_controllo_manuale_senza_ip(client, monitored):
    assert client.post(f"/api/devices/{monitored['devices']['senza-ip']['id']}/check").status_code == 422
    assert client.post("/api/devices/9999/check").status_code == 404


# ---------------------------------------------------------------- login e permessi
def test_senza_login_solo_salute_e_stato_del_login(anonymous):
    assert anonymous.get("/api/health").status_code == 200
    assert anonymous.get("/api/auth/status").json() == {"auth_enabled": True, "setup_required": False}
    assert anonymous.get("/api/devices").status_code == 401
    assert anonymous.post("/api/sites", json={"name": "x"}).status_code == 401
    assert anonymous.get("/api/auth/me").status_code == 401
    # Il primo amministratore esiste già: nessuno può crearne un altro così
    assert anonymous.post("/api/auth/setup", json={"username": "furbo", "password": "12345678"}).status_code == 409


def test_login_ruoli_e_cambio_password(client, anonymous):
    assert anonymous.post("/api/auth/login", json={"username": "admin", "password": "sbagliata"}).status_code == 401
    create(client, "/users", {"username": " Mario.Rossi ", "password": "lettore-123", "role": "viewer"})
    create(client, "/users", {"username": "tecnico", "password": "tecnico-123", "role": "editor"})
    assert client.post("/api/users", json={"username": "mario.rossi", "password": "altra-pass"}).status_code == 422
    assert "password" not in client.get("/api/users").json()["items"][0]

    # Il lettore consulta ma non modifica, e non vede gli utenti
    login = anonymous.post("/api/auth/login", json={"username": "MARIO.ROSSI", "password": "lettore-123"})
    assert login.status_code == 200 and login.json()["user"]["role"] == "viewer"
    assert anonymous.get("/api/auth/me").json()["username"] == "mario.rossi"
    assert anonymous.get("/api/sites").status_code == 200
    assert anonymous.post("/api/sites", json={"name": "x"}).status_code == 403
    assert anonymous.get("/api/users").status_code == 403

    # Il token funziona anche come Bearer (script, integrazioni)
    token = login.json()["token"]
    anonymous.cookies.clear()
    assert anonymous.get("/api/sites", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert anonymous.get("/api/sites", headers={"Authorization": "Bearer manomesso"}).status_code == 401

    # Il tecnico modifica i dati
    anonymous.post("/api/auth/login", json={"username": "tecnico", "password": "tecnico-123"})
    assert anonymous.post("/api/sites", json={"name": "Sede del tecnico"}).status_code == 201
    assert anonymous.post("/api/users", json={"username": "x", "password": "12345678"}).status_code == 403

    # Cambio password: serve quella attuale, le sessioni precedenti scadono
    old_token = anonymous.cookies.get("netmap_session")
    assert anonymous.post("/api/auth/password", json={"current_password": "no", "new_password": "nuova-pass-1"}).status_code == 422
    assert anonymous.post("/api/auth/password", json={"current_password": "tecnico-123", "new_password": "nuova-pass-1"}).status_code == 200
    assert anonymous.get("/api/sites", headers={"Authorization": f"Bearer {old_token}"}).status_code == 401
    assert anonymous.get("/api/sites").status_code == 200  # la sessione corrente ha il cookie nuovo

    anonymous.post("/api/auth/logout")
    assert anonymous.get("/api/sites").status_code == 401


def test_utente_disattivato_e_ultimo_amministratore(client, anonymous):
    user = create(client, "/users", {"username": "temp", "password": "temp-1234", "role": "editor"})
    anonymous.post("/api/auth/login", json={"username": "temp", "password": "temp-1234"})
    assert anonymous.get("/api/sites").status_code == 200
    client.patch(f"/api/users/{user['id']}", json={"active": False})
    assert anonymous.get("/api/sites").status_code == 401  # la sessione aperta smette di valere
    assert anonymous.post("/api/auth/login", json={"username": "temp", "password": "temp-1234"}).status_code == 403

    admin = next(u for u in client.get("/api/users").json()["items"] if u["username"] == ADMIN["username"])
    assert client.patch(f"/api/users/{admin['id']}", json={"role": "editor"}).status_code == 422
    assert client.patch(f"/api/users/{admin['id']}", json={"active": False}).status_code == 422
    assert client.delete(f"/api/users/{admin['id']}").status_code == 409


def test_troppi_tentativi(anonymous):
    for _ in range(5):
        assert anonymous.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401
    blocked = anonymous.post("/api/auth/login", json={"username": "admin", "password": ADMIN["password"]})
    assert blocked.status_code == 429 and blocked.headers["Retry-After"] == "60"
    assert blocked.json()["detail"] == "Troppi tentativi sbagliati: riprova tra un minuto"
    # Un altro utente dallo stesso indirizzo entra ancora
    assert anonymous.post("/api/auth/login", json={"username": "altro", "password": "x"}).status_code == 401


def test_troppi_tentativi_dallo_stesso_indirizzo(anonymous):
    for n in range(20):
        assert anonymous.post("/api/auth/login", json={"username": f"utente{n}", "password": "x"}).status_code == 401
    blocked = anonymous.post("/api/auth/login", json={"username": "admin", "password": ADMIN["password"]})
    assert blocked.status_code == 429 and blocked.json()["detail"] == "Troppi tentativi sbagliati: riprova tra 15 minuti"


def test_attesa_che_raddoppia():
    now = [0.0]
    throttle = Throttle(max_failures=3, base_lock=60, max_lock=300, window=900, clock=lambda: now[0])
    assert [throttle.failure("a") for _ in range(3)] == [0, 0, 60]
    assert throttle.retry_after("a") == 60
    now[0] += 61
    assert throttle.retry_after("a") == 0
    assert throttle.failure("a") == 120  # errore subito dopo il blocco: attesa doppia
    now[0] += 121
    assert [throttle.failure("a"), throttle.failure("a")] == [240, 300]  # fino al massimo
    now[0] += 2000  # tanto tempo senza errori: si riparte da zero
    assert throttle.retry_after("a") == 0 and throttle.failure("a") == 0
    throttle.success("a")
    assert throttle.failure("a") == 0


def test_indirizzo_del_client_dietro_i_proxy(monkeypatch):
    def request(peer, forwarded=None):
        headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
        return Request({"type": "http", "client": (peer, 1234), "headers": headers})

    monkeypatch.setattr(settings, "trusted_proxies", 0)
    assert client_ip(request("172.18.0.5", "1.2.3.4")) == "172.18.0.5"
    monkeypatch.setattr(settings, "trusted_proxies", 2)  # Caddy + nginx
    assert client_ip(request("172.18.0.5", "192.168.1.20, 172.18.0.6")) == "192.168.1.20"
    # Un client che si inventa X-Forwarded-For non cambia il risultato: Caddy aggiunge l'indirizzo vero
    assert client_ip(request("172.18.0.5", "6.6.6.6, 192.168.1.20, 172.18.0.6")) == "192.168.1.20"
    monkeypatch.setattr(settings, "trusted_proxies", 1)  # solo nginx
    assert client_ip(request("172.18.0.5", "6.6.6.6, 192.168.1.20")) == "192.168.1.20"
    assert client_ip(request("172.18.0.5")) == "172.18.0.5"


# ---------------------------------------------------------------- rack
def test_vista_frontale_del_rack(client):
    site = create(client, "/sites", {"name": "CED"})
    rack = create(client, "/racks", {"name": "R01", "site_id": site["id"], "u_height": 12})
    vendor = create(client, "/manufacturers", {"name": "Cisco"})
    model_2u = create(client, "/device-types", {"manufacturer_id": vendor["id"], "model": "ISR4431", "u_height": 2})
    role = create(client, "/device-roles", {"name": "Router", "color": "#3366CC"})
    base = {"site_id": site["id"], "rack_id": rack["id"]}
    create(client, "/devices", {**base, "name": "router", "rack_position": 10, "device_type_id": model_2u["id"], "role_id": role["id"]})
    create(client, "/devices", {**base, "name": "switch", "rack_position": 11})   # si sovrappone al router
    create(client, "/devices", {**base, "name": "patch", "rack_position": 1})
    create(client, "/devices", {**base, "name": "da-sistemare"})

    view = client.get(f"/api/racks/{rack['id']}/elevation").json()
    devices = {d["name"]: d for d in view["devices"]}
    assert view["u_height"] == 12 and view["used_units"] == 3
    assert devices["router"]["u_height"] == 2 and devices["router"]["color"] == "#3366CC"
    assert devices["router"]["conflict"] and devices["switch"]["conflict"] and not devices["patch"]["conflict"]
    assert [d["name"] for d in view["unplaced"]] == ["da-sistemare"]

    # In mappa ogni device porta con sé il suo rack, per disegnare la "bolla" del rack
    create(client, "/devices", {"site_id": site["id"], "name": "fuori-rack"})
    the_map = create(client, "/maps", {"name": "CED", "site_id": site["id"]})
    nodes = {n["name"]: n for n in client.get(f"/api/maps/{the_map['id']}/view").json()["nodes"]}
    assert (nodes["router"]["rack_id"], nodes["router"]["rack_name"], nodes["router"]["rack_position"]) == (rack["id"], "R01", 10)
    assert nodes["fuori-rack"]["rack_id"] is None and nodes["fuori-rack"]["rack_name"] is None
