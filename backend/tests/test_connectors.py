"""Import da Zabbix, LibreNMS, Observium, PRTG, GLPI e Lansweeper con server finti (risposte nella forma delle API
vere, ridotte ai campi che servono): lettura, Snapshot, scrittura con l'Importer di NetBox, API /imports."""
import json
import urllib.parse

import pytest
from sqlalchemy import select

from app.core.secrets import encrypt
from app.models import Cable, Device, DeviceRole, DeviceType, ImportRun, Interface, IPAddress, Location, Manufacturer, Site
from app.services import connectors, netbox

ZABBIX_HOSTS = [
    {"hostid": "10101", "host": "sw-core", "name": "Switch core", "status": "0", "description": "Centro stella",
     "groups": [{"groupid": "5", "name": "Switch"}],
     "interfaces": [{"ip": "10.0.0.9", "dns": "", "useip": "1", "type": "1", "main": "1"},
                    {"ip": "10.0.0.2", "dns": "sw-core.lan", "useip": "1", "type": "2", "main": "1"}],
     "inventory": {"type": "Switch", "vendor": "Cisco", "model": "C9300-48P", "serialno_a": "FOC123",
                   "asset_tag": "A-1", "location": "CED", "macaddress_a": "00:11:22:33:44:55"}},
    {"hostid": "10102", "host": "fw", "name": "fw", "status": "1", "groups": [{"groupid": "6", "name": "Firewall"}],
     "interfaces": [{"ip": "", "dns": "fw.lan", "useip": "0", "type": "1", "main": "1"}], "inventory": []},
]

LIBRENMS = {
    "system": {"status": "ok", "system": [{"local_ver": "24.9.1"}]},
    "devices": {"status": "ok", "devices": [
        {"device_id": 1, "hostname": "10.1.0.1", "sysName": "core.lan", "display": None, "ip": "10.1.0.1",
         "location": "Milano", "location_id": 3, "type": "network", "hardware": "EX4300-48T",
         "sysObjectID": ".1.3.6.1.4.1.2636.1.1.1.2.63", "serial": "JN11", "os": "junos", "version": "21.4",
         "disabled": 0},
        {"device_id": 2, "hostname": "acc1.lan", "sysName": "acc1", "display": "Accesso 1", "ip": "10.1.0.2",
         "location": "Milano", "location_id": 3, "type": "network", "hardware": "", "sysObjectID": "",
         "disabled": 0},
        {"device_id": 3, "hostname": "srv", "sysName": "srv", "ip": "", "location": "Roma", "location_id": 4,
         "type": "server", "disabled": 1},
    ]},
    "ports": {"status": "ok", "ports": [
        {"port_id": 11, "device_id": 1, "ifName": "ge-0/0/1", "ifDescr": "ge-0/0/1", "ifAlias": "verso acc1",
         "ifPhysAddress": "aa:bb:cc:00:00:01", "ifSpeed": 1000000000, "ifType": "ethernetCsmacd",
         "ifAdminStatus": "up", "ifMtu": 1514, "deleted": 0},
        {"port_id": 12, "device_id": 1, "ifName": "vlan.10", "ifType": "l3ipvlan", "ifSpeed": 0, "deleted": 0},
        {"port_id": 21, "device_id": 2, "ifName": "Gi0/1", "ifType": "ethernetCsmacd", "ifSpeed": 1000000000,
         "ifAdminStatus": "down", "deleted": 0},
        {"port_id": 22, "device_id": 2, "ifName": "Gi0/2", "ifType": "ethernetCsmacd", "deleted": 1},
    ]},
    "resources/ip/addresses": {"status": "ok", "ip_addresses": [
        {"port_id": 12, "ipv4_address": "10.1.0.1", "ipv4_prefixlen": 24}]},
    "resources/links": {"status": "ok", "links": [{"local_port_id": 11, "remote_port_id": 21}]},
}

PRTG_DEVICES = [
    {"objid": 2001, "device": "Switch piano 1", "host": "10.2.0.11", "group": "Piano 1", "probe": "Sonda Torino",
     "tags": "switch cisco", "active": True},
    {"objid": 2002, "device": "Router", "host": "router.torino.lan", "group": "Sonda Torino", "probe": "Sonda Torino",
     "tags": "", "active": False},
    {"objid": 2003, "device": "NAS", "host": "10.3.0.5", "group": "Server", "probe": "Sonda locale", "active": True},
]

GLPI = {
    "NetworkEquipment": [
        {"id": 1, "name": "sw-glpi-1", "locations_id": "Bologna > Edificio A > CED", "manufacturers_id": "HPE",
         "networkequipmentmodels_id": "Aruba 2930F", "networkequipmenttypes_id": "Switch", "serial": "CN01",
         "otherserial": "INV-9", "comment": "", "is_deleted": 0, "is_template": 0},
        {"id": 2, "name": "sw-glpi-2", "locations_id": "Bologna", "manufacturers_id": 0,
         "networkequipmentmodels_id": 0, "networkequipmenttypes_id": 0, "is_deleted": 0, "is_template": 0},
        {"id": 3, "name": "cestinato", "locations_id": "Bologna", "is_deleted": 1, "is_template": 0},
    ],
    "NetworkPort": [
        {"id": 31, "itemtype": "NetworkEquipment", "items_id": 1, "name": "1", "logical_number": 1,
         "mac": "00:aa:00:00:00:01", "instantiation_type": "NetworkPortEthernet", "is_deleted": 0},
        {"id": 32, "itemtype": "NetworkEquipment", "items_id": 1, "name": "Management", "logical_number": 0,
         "instantiation_type": "NetworkPortLocal", "is_deleted": 0},
        {"id": 33, "itemtype": "NetworkEquipment", "items_id": 2, "name": "24", "logical_number": 24,
         "instantiation_type": "NetworkPortFiberchannel", "is_deleted": 0},
        {"id": 34, "itemtype": "Computer", "items_id": 1, "name": "eth0", "is_deleted": 0},
    ],
    "NetworkName": [{"id": 41, "itemtype": "NetworkPort", "items_id": 32, "name": "sw-glpi-1"}],
    "IPAddress": [{"id": 51, "itemtype": "NetworkName", "items_id": 41, "name": "10.4.0.10", "is_deleted": 0}],
    "NetworkPort_NetworkPort": [{"id": 61, "networkports_id_1": 31, "networkports_id_2": 33}],
}

LANSWEEPER_SITES = [{"id": "s-1", "name": "Napoli"}, {"id": "s-2", "name": "Bari"}]
LANSWEEPER_ASSETS = {
    "s-1": [
        {"key": "k1", "assetBasicInfo": {"name": "ap-napoli", "type": "Wireless Access Point", "ipAddress": "10.5.0.20",
                                         "mac": "00:bb:00:00:00:01", "description": ""},
         "assetCustom": {"manufacturer": "Ubiquiti", "model": "U6-Pro", "serialNumber": "UB1", "location": "Sala"}},
        {"key": "k2", "assetBasicInfo": {"name": "pc-mario", "type": "Windows", "ipAddress": "10.5.0.100"},
         "assetCustom": {}},
    ],
    "s-2": [],
}


class FakeServers:
    """Sostituisce HttpSource.http: risponde secondo il percorso; ricorda le richieste."""

    def __init__(self):
        self.requests: list[tuple[str, dict, dict | None]] = []

    def __call__(self, source, url, headers=None, data=None, method=None):
        body = json.loads(data) if data else None
        self.requests.append((url, headers or {}, body))
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        path = parts.path
        answer, extra = self.route(source.key, path, query, headers or {}, body), {}
        if isinstance(answer, tuple):
            answer, extra = answer
        return json.dumps(answer).encode(), extra

    def route(self, key, path, query, headers, body):
        if key == "zabbix":
            method = body["method"]
            if method == "apiinfo.version":
                return {"jsonrpc": "2.0", "result": "6.0.20", "id": 1}
            if method == "user.login":
                ok = body["params"] == {"username": "admin", "password": "zabbix"}
                return {"jsonrpc": "2.0", "result": "sessione", "id": 1} if ok else \
                    {"jsonrpc": "2.0", "error": {"code": -32602, "message": "Invalid params.",
                                                 "data": "Incorrect user name or password or account is temporarily blocked."}}
            assert body.get("auth") == "sessione"
            if method == "user.logout":
                return {"jsonrpc": "2.0", "result": True, "id": 1}
            hosts = ZABBIX_HOSTS
            if "groupids" in body["params"]:
                hosts = [h for h in hosts if any(g["groupid"] in body["params"]["groupids"] for g in h["groups"])]
            return {"jsonrpc": "2.0", "result": hosts, "id": 1}
        if key in ("librenms", "observium"):
            name = path.split("/api/v0/", 1)[1].strip("/")
            if key == "observium":
                assert headers["Authorization"].startswith("Basic ")
                data = LIBRENMS[name]
                return {**data, name: {str(x.get("device_id") or x.get("port_id")): x for x in data[name]}}
            assert headers["X-Auth-Token"] == "tok"
            return LIBRENMS[name]
        if key == "prtg":
            assert query.get("apitoken") == "tok"
            if path.endswith("status.json"):
                return {"Version": "24.2.96.1375"}
            return {"prtg-version": "24.2", "treesize": 3, "devices": PRTG_DEVICES}
        if key == "glpi":
            name = path.rsplit("/", 1)[1]
            assert headers.get("App-Token") == "app"
            if name == "initSession":
                assert headers["Authorization"] == "user_token tok"
                return {"session_token": "s3ss"}
            assert headers["Session-Token"] == "s3ss"
            if name == "killSession":
                return True
            if name == "getGlpiConfig":
                return {"cfg_glpi": {"version": "10.0.16"}}
            start, end = map(int, query["range"].split("-"))
            items = GLPI[name]
            return items[start:end + 1], {"Content-Range": f"{start}-{min(end, len(items) - 1)}/{len(items)}"}
        if key == "lansweeper":
            assert headers["Authorization"] == "Token tok"
            if "authorizedSites" in body["query"]:
                return {"data": {"authorizedSites": {"sites": LANSWEEPER_SITES}}}
            variables = body["variables"]
            items = LANSWEEPER_ASSETS[variables["site"]]
            limit = variables["pagination"]["limit"]
            return {"data": {"site": {"assetResources": {
                "total": len(items), "pagination": {"limit": limit, "current": None, "next": None, "page": "FIRST"},
                "items": items[:limit]}}}}
        raise AssertionError(key)


@pytest.fixture
def servers(monkeypatch):
    fake = FakeServers()
    monkeypatch.setattr(connectors.HttpSource, "http", lambda self, url, headers=None, data=None, method=None:
                        fake(self, url, headers, data, method))
    return fake


def run_import(db, source, url, secrets, username=None, groups=(), default_site=None, dry_run=False):
    run = ImportRun(source=source, url=url, token_enc=encrypt(json.dumps(secrets)), username=username,
                    verify_tls=True, site_ids=list(groups), default_site=default_site, dry_run=dry_run)
    db.add(run)
    db.commit()
    return netbox.execute_import(db, run.id)


def devices(db):
    return {d.name: d for d in db.scalars(select(Device))}


def names(db, device):
    """Nomi di sede, posizione, ruolo, produttore e modello del device (il modello non ha relazioni)."""
    get = lambda model, id_: db.get(model, id_) if id_ else None  # noqa: E731
    location, device_type = get(Location, device.location_id), get(DeviceType, device.device_type_id)
    maker = get(Manufacturer, device_type.manufacturer_id) if device_type else None
    role = get(DeviceRole, device.role_id)
    return {"site": db.get(Site, device.site_id).name, "location": location.path if location else None,
            "role": role.name if role else None, "maker": maker.name if maker else None,
            "model": device_type.model if device_type else None}


def test_zabbix(session_factory, servers):
    source = connectors.build("zabbix", "https://zabbix.lan/zabbix", {"token": "zabbix"}, "admin", True)
    probe = source.probe()
    assert probe["version"] == "6.0.20" and probe["counts"]["devices"] == 2
    assert [g["name"] for g in probe["groups"]] == ["Firewall", "Switch"]
    assert servers.requests[0][0] == "https://zabbix.lan/zabbix/api_jsonrpc.php"

    db = session_factory()
    run = run_import(db, "zabbix", "https://zabbix.lan/zabbix", {"token": "zabbix"}, "admin", default_site="Sede")
    assert run.status == "done", run.log
    assert "Connessione a Zabbix 6.0.20" in run.log and run.source_version == "6.0.20" and run.netbox_version is None
    found = devices(db)
    assert set(found) == {"Switch core", "fw"}
    core = found["Switch core"]
    assert core.source == "zabbix" and core.serial == "FOC123" and core.asset_tag == "A-1" and core.status == "active"
    assert names(db, core) == {"site": "Sede", "location": "CED", "role": "Switch", "maker": "Cisco",
                               "model": "C9300-48P"}
    assert core.management_ip == "10.0.0.2/32"  # SNMP prima dell'agente
    assert core.custom_fields == {"zabbix_host": "sw-core"}
    assert found["fw"].status == "offline" and found["fw"].management_ip is None  # solo DNS
    assert any(r[2] and r[2]["method"] == "user.logout" for r in servers.requests)

    run = run_import(db, "zabbix", "https://zabbix.lan/zabbix", {"token": "sbagliata"}, "admin")
    assert run.status == "failed" and "Zabbix rifiuta le credenziali: Incorrect user name" in run.log


def test_zabbix_gruppo_scelto(session_factory, servers):
    db = session_factory()
    run = run_import(db, "zabbix", "https://zabbix.lan", {"token": "zabbix"}, "admin", groups=["6"])
    assert run.status == "done", run.log
    assert set(devices(db)) == {"fw"} and run.site_names == ["Firewall"]
    assert db.scalar(select(Site.name)) == "Zabbix"  # senza sede predefinita: il nome della sorgente


def test_librenms(session_factory, servers):
    source = connectors.build("librenms", "https://nms.lan/api/v0", {"token": "tok"}, None, True)
    probe = source.probe()
    assert probe["version"] == "24.9.1"
    assert probe["groups"] == [{"id": 3, "name": "Milano", "devices": 2}, {"id": 4, "name": "Roma", "devices": 1}]

    db = session_factory()
    run = run_import(db, "librenms", "https://nms.lan", {"token": "tok"}, groups=[3])
    assert run.status == "done", run.log
    assert run.site_names == ["Milano"]
    found = devices(db)
    assert set(found) == {"core.lan", "Accesso 1"}
    core = found["core.lan"]
    assert core.serial == "JN11" and names(db, core) == {"site": "Milano", "location": None, "role": "Rete",
                                                          "maker": "Juniper", "model": "EX4300-48T"}
    assert core.custom_fields == {"os": "junos", "os_version": "21.4"}
    assert core.management_ip == "10.1.0.1/24"  # sull'IP della porta vlan.10, niente porta "mgmt"
    ports = {p.name: p for p in db.scalars(select(Interface).where(Interface.device_id == core.id))}
    assert set(ports) == {"ge-0/0/1", "vlan.10"}
    assert ports["ge-0/0/1"].type == "copper" and ports["ge-0/0/1"].speed_mbps == 1000
    assert ports["ge-0/0/1"].description == "verso acc1" and ports["vlan.10"].type == "virtual"
    access_ports = {p.name: p for p in db.scalars(select(Interface).where(Interface.device_id == found["Accesso 1"].id))}
    assert access_ports["Gi0/1"].enabled is False and "Gi0/2" not in access_ports  # cancellata in LibreNMS
    assert "mgmt" in access_ports and found["Accesso 1"].management_ip == "10.1.0.2/32"
    cable = db.scalar(select(Cable))
    assert {cable.a_interface.name, cable.b_interface.name} == {"ge-0/0/1", "Gi0/1"}

    run = run_import(db, "librenms", "https://nms.lan", {"token": "tok"})
    assert run.status == "done" and run.counts["device"] == {"created": 1, "existing": 2, "failed": 0, "skipped": 0}
    assert devices(db)["srv"].status == "offline"


def test_observium(session_factory, servers):
    db = session_factory()
    run = run_import(db, "observium", "https://observium.lan", {"token": "pw"}, "admin")
    assert run.status == "done", run.log
    assert len(devices(db)) == 3 and db.scalar(select(Cable)) is None
    assert devices(db)["core.lan"].management_ip == "10.1.0.1/32"


def test_prtg(session_factory, servers):
    source = connectors.build("prtg", "https://prtg.lan", {"token": "tok"}, None, True)
    assert [(g["name"], g["devices"]) for g in source.probe()["groups"]] == [("Sonda locale", 1), ("Sonda Torino", 2)]

    db = session_factory()
    run = run_import(db, "prtg", "https://prtg.lan", {"token": "tok"}, groups=["Sonda Torino"])
    assert run.status == "done", run.log
    found = devices(db)
    assert set(found) == {"Switch piano 1", "Router"}
    switch = found["Switch piano 1"]
    assert names(db, switch)["site"] == "Sonda Torino" and names(db, switch)["location"] == "Piano 1"
    assert switch.management_ip == "10.2.0.11/32" and switch.custom_fields == {"prtg_tags": "switch cisco"}
    router = found["Router"]
    assert router.location_id is None and router.status == "offline" and router.management_ip is None
    assert router.description == "Host: router.torino.lan"


def test_glpi(session_factory, servers, monkeypatch):
    monkeypatch.setattr(connectors, "PAGE", 2)  # più pagine
    db = session_factory()
    run = run_import(db, "glpi", "https://glpi.lan/", {"token": "tok", "app_token": "app"})
    assert run.status == "done", run.log
    assert run.source_version == "10.0.16"
    found = devices(db)
    assert set(found) == {"sw-glpi-1", "sw-glpi-2"}
    first = found["sw-glpi-1"]
    assert names(db, first) == {"site": "Bologna", "location": "Edificio A › CED", "role": "Switch", "maker": "HPE",
                                "model": "Aruba 2930F"}
    assert first.asset_tag == "INV-9" and first.management_ip == "10.4.0.10/32"
    ip = db.scalar(select(IPAddress).where(IPAddress.host == "10.4.0.10"))
    assert ip.interface.name == "Management" and ip.interface.type == "virtual" and ip.dns_name == "sw-glpi-1"
    assert found["sw-glpi-2"].device_type_id is None and found["sw-glpi-2"].location_id is None
    cable = db.scalar(select(Cable))
    assert {cable.a_interface.name, cable.b_interface.name} == {"1", "24"}
    assert {p.type for p in db.scalars(select(Interface).where(Interface.name == "24"))} == {"fiber"}
    assert db.scalar(select(Location).where(Location.name == "Edificio A")) is not None
    assert servers.requests[-1][0].endswith("/apirest.php/killSession")


def test_lansweeper(session_factory, servers):
    source = connectors.build("lansweeper", "", {"token": "tok"}, None, True)
    assert source.probe()["groups"] == [{"id": "s-2", "name": "Bari", "devices": 0},
                                        {"id": "s-1", "name": "Napoli", "devices": 2}]
    assert servers.requests[0][0] == connectors.Lansweeper.DEFAULT_URL

    db = session_factory()
    run = run_import(db, "lansweeper", "", {"token": "tok"}, groups=["s-1"])
    assert run.status == "done", run.log
    assert "2 asset, 1 apparati di rete" in run.log
    ap = devices(db)["ap-napoli"]
    assert set(devices(db)) == {"ap-napoli"} and ap.management_ip == "10.5.0.20/32"
    assert names(db, ap) == {"site": "Napoli", "location": "Sala", "role": "Wireless Access Point",
                             "maker": "Ubiquiti", "model": "U6-Pro"}


def test_api(client, servers, session_factory):
    connection = {"source": "prtg", "url": "https://prtg.lan", "token": "tok"}
    probe = client.post("/api/imports/test", json=connection)
    assert probe.status_code == 200, probe.text
    assert probe.json()["version"] == "24.2.96.1375" and probe.json()["groups"][1]["id"] == "Sonda Torino"
    assert client.post("/api/imports/test", json={**connection, "url": "prtg"}).status_code == 422
    assert client.post("/api/imports/test", json={**connection, "source": "boh"}).status_code == 422

    created = client.post("/api/imports", json={**connection, "group_ids": ["Sonda Torino"],
                                                "default_site": "Altro", "username": " "})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["source"] == "prtg" and body["site_ids"] == ["Sonda Torino"] and body["default_site"] == "Altro"
    assert body["username"] is None and "tok" not in created.text
    assert client.post("/api/imports", json=connection).status_code == 409
    db = session_factory()
    run = netbox.execute_import(db, body["id"])
    assert run.status == "done", run.log
    listed = client.get("/api/imports").json()
    assert listed[0]["source_version"] == "24.2.96.1375" and listed[0]["status"] == "done"
    assert client.get(f"/api/imports/{body['id']}").json()["counts"]["device"]["created"] == 2
