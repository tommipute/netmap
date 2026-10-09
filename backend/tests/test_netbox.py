"""Import da NetBox, con un NetBox finto che risponde come le API vere (pagine comprese)."""
import io
import json
import urllib.error

import pytest
from sqlalchemy import func, select

from app.core.secrets import decrypt, encrypt
from app.models import (
    VLAN, VRF, AuditEntry, Cable, Device, DeviceRole, DeviceType, ImportRun, Interface, IPAddress, Location, Prefix, Rack, Site,
    StackMember,
)
from app.services import netbox
from tests.test_discovery import create

TOKEN = "0123456789abcdef0123456789abcdef01234567"


def ref(id_, **extra):
    return {"id": id_, **extra}


def iface(id_, device, device_name, name, site, type_="1000base-t", cable=None, peers_type=None, peers=(),
          endpoints_type=None, endpoints=(), **extra):
    return {
        "id": id_, "device": ref(device, name=device_name), "name": name, "type": {"value": type_},
        "enabled": True, "mgmt_only": False, "cable": ref(cable) if cable else None,
        "link_peers_type": peers_type, "link_peers": [ref(p, device={"name": d}) for p, d in peers],
        "connected_endpoints_type": endpoints_type, "connected_endpoints": [ref(e) for e in endpoints],
        "_site": site, **extra,
    }


# Milano (1): router, stack di due switch, patch panel. Roma (2): uno switch.
DATA = {
    "dcim/sites": [
        {"id": 1, "name": "Milano", "physical_address": "Via Roma 1", "device_count": 4, "custom_fields": {}},
        {"id": 2, "name": "Roma", "device_count": 1},
    ],
    "dcim/locations": [
        {"id": 11, "name": "Piano 1", "site": ref(1), "parent": ref(10), "_depth": 1},
        {"id": 10, "name": "Palazzina A", "site": ref(1), "parent": None, "_depth": 0},
    ],
    "dcim/racks": [{"id": 20, "name": "R1", "site": ref(1), "location": ref(11), "u_height": 42}],
    "dcim/manufacturers": [{"id": 30, "name": "Cisco"}, {"id": 31, "name": "Panduit"}],
    "dcim/device-roles": [
        {"id": 40, "name": "Access Switch", "color": "10b981"},
        {"id": 41, "name": "Router", "color": "e24b4b"},
        {"id": 42, "name": "Patch Panel", "color": "zzz"},
        {"id": 43, "name": "Server"},  # nessun device: con le sedi scelte non si importa
    ],
    "dcim/device-types": [
        {"id": 50, "manufacturer": ref(30), "model": "C9300-48P", "u_height": 1},
        {"id": 51, "manufacturer": ref(30), "model": "ISR4331", "u_height": 1.5},
        {"id": 52, "manufacturer": ref(31), "model": "PP-24", "u_height": 1},
    ],
    "ipam/vrfs": [{"id": 55, "name": "MGMT", "rd": "65000:1"}],
    "ipam/vlan-groups": [{"id": 60, "scope_type": "dcim.site", "scope_id": 1}],
    "ipam/vlans": [
        {"id": 70, "vid": 10, "name": "Uffici", "site": ref(1), "status": {"value": "active"}},
        {"id": 71, "vid": 20, "name": "Voce", "group": ref(60), "status": {"value": "reserved"}},
        {"id": 72, "vid": 30, "name": "Roma", "site": ref(2)},
        {"id": 73, "vid": 99, "name": "Globale"},
    ],
    "ipam/prefixes": [
        {"id": 80, "prefix": "10.1.0.0/24", "scope_type": "dcim.site", "scope_id": 1, "vlan": ref(70),
         "status": {"value": "container"}},
        {"id": 81, "prefix": "10.2.0.0/24", "scope_type": "dcim.site", "scope_id": 2},
        {"id": 82, "prefix": "172.16.0.0/24", "vrf": ref(55), "scope_type": "dcim.location", "scope_id": 11},
    ],
    "dcim/virtual-chassis": [{"id": 90, "name": "stack-p1", "master": ref(101)}],
    "dcim/devices": [
        {"id": 100, "name": "rtr01", "site": ref(1), "rack": ref(20), "position": 40.0, "device_type": ref(51, model="ISR4331"),
         "role": ref(41), "status": {"value": "active"}, "primary_ip4": ref(200), "location": ref(11)},
        {"id": 102, "name": "sw-p1-2", "site": ref(1), "rack": ref(20), "position": 11.0,
         "device_type": ref(50, model="C9300-48P"), "role": ref(40), "virtual_chassis": ref(90), "vc_position": 2,
         "serial": "FOC2"},
        {"id": 101, "name": "sw-p1-1", "site": ref(1), "rack": ref(20), "position": 10.0,
         "device_type": ref(50, model="C9300-48P"), "role": ref(40), "virtual_chassis": ref(90), "vc_position": 1,
         "serial": "FOC1", "asset_tag": "A-1", "custom_fields": {"contratto": "CN-1", "vuoto": None},
         "status": {"value": "staged"}, "primary_ip4": ref(201)},
        {"id": 103, "name": None, "display": "PP-24 (103)", "site": ref(1), "rack": ref(20), "position": 20,
         "device_type": ref(52, model="PP-24"), "role": ref(42)},
        {"id": 104, "name": "sw-roma", "site": ref(2), "device_type": ref(50, model="C9300-48P"), "role": ref(40)},
    ],
    "dcim/interfaces": [
        iface(1000, 100, "rtr01", "Gi0/0/0", 1, cable=500, peers_type="dcim.interface", peers=[(1010, "sw-p1-1")],
              endpoints_type="dcim.interface", endpoints=[1010]),
        iface(1001, 100, "rtr01", "Po1", 1, type_="lag"),
        iface(1002, 100, "rtr01", "Gi0/0/1", 1, lag=ref(1001)),
        iface(1003, 100, "rtr01", "Gi0/0/2", 1, lag=ref(1001)),
        iface(1004, 100, "rtr01", "Loopback0", 1, type_="virtual"),
        iface(1005, 100, "rtr01", "Gi0/0/3", 1, cable=503, peers_type="dcim.frontport", peers=[(3001, "PP-24 (103)")],
              endpoints_type="dcim.interface", endpoints=[1012]),
        iface(1010, 101, "sw-p1-1", "Gi1/0/1", 1, cable=500, peers_type="dcim.interface", peers=[(1000, "rtr01")],
              endpoints_type="dcim.interface", endpoints=[1000], mode={"value": "access"}, untagged_vlan=ref(70),
              primary_mac_address={"mac_address": "00:11:22:33:44:55"}, speed=1000000, mtu=1500,
              description="Verso il router"),
        iface(1011, 101, "sw-p1-1", "Gi1/0/2", 1, type_="10gbase-x-sfpp", mode={"value": "tagged"},
              untagged_vlan=ref(70), tagged_vlans=[ref(70), ref(71), ref(72)]),
        iface(1012, 102, "sw-p1-2", "Gi2/0/1", 1, cable=502, peers_type="dcim.frontport", peers=[(3000, "PP-24 (103)")],
              endpoints_type="dcim.interface", endpoints=[1005]),
        iface(1013, 101, "sw-p1-1", "Gi1/0/48", 1, cable=504, peers_type="circuits.circuittermination", peers=[(4000, "")]),
        iface(1014, 101, "sw-p1-1", "Vlan100", 1, type_="virtual"),
        iface(1020, 104, "sw-roma", "Gi1/0/1", 2),
    ],
    "dcim/cables": [
        {"id": 500, "type": "cat6", "status": {"value": "connected"}, "label": "C-500", "color": "2196f3",
         "length": 2, "length_unit": {"value": "m"}, "_site": 1},
        {"id": 502, "type": "cat6", "status": {"value": "planned"}, "length": 150, "length_unit": {"value": "cm"},
         "_site": 1},
        {"id": 503, "type": "cat6", "_site": 1},
        {"id": 504, "type": "smf", "_site": 1},
    ],
    "ipam/ip-addresses": [
        {"id": 200, "address": "10.1.0.1/24", "assigned_object_type": "dcim.interface", "assigned_object_id": 1004,
         "dns_name": "rtr01.prova.lan", "status": {"value": "active"}},
        {"id": 201, "address": "10.1.0.2/24", "assigned_object_type": "dcim.interface", "assigned_object_id": 1014},
        {"id": 202, "address": "10.1.0.50/24", "status": {"value": "reserved"}, "description": "Stampante"},
        {"id": 203, "address": "10.2.0.1/24", "assigned_object_type": "dcim.interface", "assigned_object_id": 1020},
        {"id": 204, "address": "10.9.9.9/24", "status": {"value": "slaac"}},
        {"id": 205, "address": "172.16.0.1/24", "vrf": ref(55), "status": {"value": "dhcp"}},
    ],
}
SITE_FILTERED = {"dcim/locations", "dcim/racks", "dcim/devices", "dcim/interfaces", "dcim/cables"}


class FakeNetBox(netbox.Client):
    """Risponde con DATA come NetBox: pagine da 3 (meno di quelle chieste), filtri per sede e per id."""
    PAGE = 3
    requests: list[tuple[str, dict]] = []

    def __init__(self, url, token, verify_tls=True, version="4.2.1", data=DATA):
        super().__init__(url, token, verify_tls)
        self.netbox_version, self.data = version, data

    def get(self, path, params=None):
        params = params or {}
        FakeNetBox.requests.append((path, params))
        if path == "status":
            return {"netbox-version": self.netbox_version}
        items = self.data[path]
        if "id" in params:
            items = [x for x in items if x["id"] in params["id"]]
        if "site_id" in params and path in SITE_FILTERED:
            items = [x for x in items if (x.get("_site") or (x.get("site") or {}).get("id")) in params["site_id"]]
        offset, limit = params.get("offset", 0), min(params.get("limit", 50), self.PAGE)
        page = items[offset:offset + limit]
        return {"count": len(items), "next": "…" if offset + limit < len(items) else None, "results": page}


def queue(db, site_ids=(), dry_run=False, token=TOKEN):
    run = ImportRun(url="http://netbox.prova.lan", token_enc=encrypt(token), verify_tls=True,
                    site_ids=list(site_ids), dry_run=dry_run)
    db.add(run)
    db.commit()
    return run.id


def counts(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_traduzione_dei_valori():
    assert netbox.interface_type("1000base-t") == "copper"
    assert netbox.interface_type("10gbase-x-sfpp") == "fiber"
    assert netbox.interface_type("25gbase-x-sfp28") == "fiber"
    assert netbox.interface_type("10gbase-kr") == "other"  # backplane
    assert netbox.interface_type("cisco-stackwise-480") == "other"
    assert netbox.interface_type("ieee802.11ax") == "wireless"
    assert netbox.interface_type("virtual") == "virtual" and netbox.interface_type("lag") == "lag"
    assert netbox.interface_mode("tagged-all") == "trunk" and netbox.interface_mode(None) is None
    assert netbox.cable_type("cat5e") == "cat5e" and netbox.cable_type("cat7") == "cat6a"
    assert netbox.cable_type("mmf-om4") == "fiber_mm" and netbox.cable_type("smf-os2") == "fiber_sm"
    assert netbox.cable_type("dac-active") == "dac" and netbox.cable_type("") is None
    assert netbox.cable_type("power") == "other"
    assert netbox.cable_length(1.5, "km") == (1500, "m")
    assert netbox.cable_length(24, "in") == (2, "ft")
    assert netbox.cable_length(0, "m") == (None, "m") and netbox.cable_length(None, None) == (None, "m")
    assert netbox.normalize_url(" https://netbox.prova.lan/api/ ") == "https://netbox.prova.lan"
    with pytest.raises(netbox.NetBoxError):
        netbox.normalize_url("netbox.prova.lan")
    assert netbox.Client("http://nb", TOKEN).headers["Authorization"] == f"Token {TOKEN}"
    assert netbox.Client("http://nb", " nbt_abc.def ").headers["Authorization"] == "Bearer nbt_abc.def"


def test_errori_della_connessione(monkeypatch):
    def answer(code=None, body=b"", reason=None):
        def urlopen(request, timeout, context):
            if code:
                raise urllib.error.HTTPError(request.full_url, code, "errore", {}, io.BytesIO(body))
            if reason:
                raise urllib.error.URLError(reason)
            return io.BytesIO(body)
        monkeypatch.setattr(netbox.urllib.request, "urlopen", urlopen)

    client = netbox.Client("http://nb", TOKEN)
    cases = [
        (dict(code=403, body=b'{"detail": "Invalid token"}'), "NetBox rifiuta il token (Invalid token)"),
        (dict(code=404), "NetBox non trova /api/status/"),
        (dict(code=500), "NetBox ha risposto 500 su /api/status/"),
        (dict(reason=ConnectionRefusedError("Connection refused")), "NetBox non risponde"),
        (dict(body=b"<html>"), "La risposta non è JSON"),
        (dict(body=b'{"netbox-version": "3.2.9"}'), "NetBox 3.2.9 è troppo vecchio"),
        (dict(body=b"{}"), "Non sembra NetBox"),
    ]
    for kwargs, message in cases:
        answer(**kwargs)
        with pytest.raises(netbox.NetBoxError, match=message.replace("(", r"\(").replace(")", r"\)")):
            client.version()
    answer(body=json.dumps({"netbox-version": "4.2.1-Docker-3.2.0"}).encode())
    assert client.version() == "4.2.1-Docker-3.2.0"


def test_simulazione_poi_import_di_una_sede(session_factory):
    db = session_factory()
    run = netbox.execute_import(db, queue(db, site_ids=[1], dry_run=True), FakeNetBox)
    assert run.status == "done", run.log
    assert run.netbox_version == "4.2.1" and run.site_names == ["Milano"] and run.token_enc is None
    assert run.counts["device"]["created"] == 3  # router, stack, patch panel
    assert "Fine della simulazione (niente è stato salvato): " in run.log
    assert counts(db, Device) == 0 and counts(db, Site) == 0 and counts(db, AuditEntry) == 0

    run = netbox.execute_import(db, queue(db, site_ids=[1]), FakeNetBox)
    assert run.status == "done", run.log
    assert run.problems == []
    assert "Fine: " in run.log and "Cavi non importati: 1 verso circuiti, prese elettriche o console" in run.log
    assert {s.name for s in db.scalars(select(Site))} == {"Milano"}
    assert run.counts["device_role"]["created"] == 3  # "Server" non serve a nessun device della sede
    # Posizioni annidate e rack nella posizione
    piano = db.scalar(select(Location).where(Location.name == "Piano 1"))
    assert piano.path == "Palazzina A › Piano 1"
    rack = db.scalar(select(Rack))
    assert rack.location_id == piano.id and rack.u_height == 42

    devices = {x.name: x for x in db.scalars(select(Device))}
    assert set(devices) == {"rtr01", "stack-p1", "PP-24 (103)"}
    stack = devices["stack-p1"]
    assert stack.serial == "FOC1" and stack.asset_tag == "A-1" and stack.status == "planned"
    assert stack.custom_fields == {"contratto": "CN-1"} and stack.rack_position == 10
    members = db.scalars(select(StackMember).where(StackMember.device_id == stack.id).order_by(StackMember.number)).all()
    assert [(m.number, m.serial, m.rack_position, m.model) for m in members] == [
        (1, "FOC1", 10, "C9300-48P"), (2, "FOC2", 11, "C9300-48P")]
    assert devices["rtr01"].location_id == piano.id and devices["rtr01"].rack_position == 40
    assert db.get(DeviceType, devices["rtr01"].device_type_id).u_height == 2  # 1,5 U arrotondato in su
    roles = {r.name: r for r in db.scalars(select(DeviceRole))}
    assert roles["Router"].color == "#E24B4B" and roles["Router"].level == 0
    assert roles["Patch Panel"].color == "#888780"  # colore di NetBox non valido: quello indovinato dal nome

    ports = {(p.device.name, p.name): p for p in db.scalars(select(Interface))}
    assert ("stack-p1", "Gi2/0/1") in ports  # le porte del secondo membro vanno sul device dello stack
    access = ports[("stack-p1", "Gi1/0/1")]
    assert (access.mode, access.mac_address, access.speed_mbps, access.mtu, access.description) == (
        "access", "00:11:22:33:44:55", 1000, 1500, "Verso il router")
    vlans = {v.vid: v for v in db.scalars(select(VLAN))}
    assert set(vlans) == {10, 20, 99}  # 30 è di Roma; 99 è globale
    assert vlans[20].site_id == stack.site_id and vlans[20].status == "reserved" and vlans[99].site_id is None
    assert access.untagged_vlan_id == vlans[10].id
    trunk = ports[("stack-p1", "Gi1/0/2")]
    assert trunk.mode == "trunk" and trunk.type == "fiber" and sorted(v.vid for v in trunk.tagged_vlans) == [10, 20]
    lag = ports[("rtr01", "Po1")]
    assert lag.type == "lag" and ports[("rtr01", "Gi0/0/1")].lag_id == lag.id == ports[("rtr01", "Gi0/0/2")].lag_id

    cables = {(c.a_interface.name, c.b_interface.name): c for c in db.scalars(select(Cable))}
    assert len(cables) == 2
    direct = next(c for c in cables.values() if c.label == "C-500")
    assert (direct.type, direct.color.lower(), float(direct.length), direct.length_unit) == ("cat6", "#2196f3", 2, "m")
    patched = next(c for c in cables.values() if c.label is None)
    assert {patched.a_interface.name, patched.b_interface.name} == {"Gi0/0/3", "Gi2/0/1"}
    assert patched.description == "Attraverso il patch panel PP-24 (103)"

    prefixes = {p.prefix: p for p in db.scalars(select(Prefix))}
    assert set(prefixes) == {"10.1.0.0/24", "172.16.0.0/24"}  # 172.16 è di una posizione di Milano
    assert prefixes["10.1.0.0/24"].vlan_id == vlans[10].id and db.get(VRF, prefixes["172.16.0.0/24"].vrf_id).name == "MGMT"
    ips = {ip.address: ip for ip in db.scalars(select(IPAddress))}
    # 10.2.0.1 è su una porta di Roma, 10.9.9.9 è libero fuori dalle subnet di Milano
    assert set(ips) == {"10.1.0.1/24", "10.1.0.2/24", "10.1.0.50/24", "172.16.0.1/24"}
    assert ips["10.1.0.1/24"].is_primary and ips["10.1.0.1/24"].dns_name == "rtr01.prova.lan"
    assert ips["10.1.0.2/24"].is_primary and ips["10.1.0.2/24"].interface.device_id == stack.id
    assert ips["10.1.0.50/24"].status == "reserved" and ips["172.16.0.1/24"].status == "dhcp"
    # Origine "netbox" per l'icona (device, membri, porte, cavi, IP)
    for model in (Device, StackMember, Interface, Cable, IPAddress):
        assert set(db.scalars(select(model.source))) == {"netbox"}, model

    # Storico: una riga per device (porte e IP compresi), con l'origine "netbox"
    sources = set(db.scalars(select(AuditEntry.source)))
    assert sources == {"netbox"}
    assert counts(db, AuditEntry) < 40
    assert db.scalar(select(func.count()).where(AuditEntry.object_type == "interface")) == 0

    # Di nuovo: c'è già tutto
    again = netbox.execute_import(db, queue(db, site_ids=[1]), FakeNetBox)
    assert again.status == "done", again.log
    assert sum(c["created"] for c in again.counts.values()) == 0 and again.problems == []
    assert again.counts["cable"]["existing"] == 2 and again.counts["interface"]["existing"] == 11
    db.close()


def test_import_di_tutto_sopra_dati_esistenti(session_factory):
    db = session_factory()
    milano = Site(name="milano")  # stessa sede, maiuscole diverse
    db.add(milano)
    db.flush()
    db.add(Device(name="RTR01", site_id=milano.id, asset_tag="A-1"))  # c'era già, con l'asset tag dello stack
    db.commit()
    FakeNetBox.requests = []
    run = netbox.execute_import(db, queue(db), FakeNetBox)
    assert run.status == "done", run.log
    assert not any("site_id" in params for _, params in FakeNetBox.requests)  # tutte le sedi: nessun filtro
    assert counts(db, Site) == 2 and run.counts["site"] == {"created": 1, "existing": 1, "failed": 0, "skipped": 0}
    router = db.scalar(select(Device).where(Device.name == "RTR01"))
    # Il device che c'era resta com'era: niente porte nuove, e i cavi verso di lui saltano
    assert counts(db, Interface) == 6 and run.counts["interface"]["skipped"] == 6
    assert db.scalar(select(func.count()).select_from(Interface).where(Interface.device_id == router.id)) == 0
    assert counts(db, Cable) == 0
    stack = db.scalar(select(Device).where(Device.name == "stack-p1"))
    assert stack.asset_tag is None
    assert {"kind": "device", "name": "stack-p1", "message": "Asset tag A-1 già usato da RTR01: importato senza"} in run.problems
    ips = {ip.address: ip for ip in db.scalars(select(IPAddress))}
    assert {"10.2.0.1/24", "10.9.9.9/24"} <= set(ips)
    # 10.1.0.1 sta su una porta di RTR01 che non è stata importata: l'IP c'è, senza porta né management
    assert ips["10.1.0.1/24"].interface_id is None and not ips["10.1.0.1/24"].is_primary
    assert {v.vid for v in db.scalars(select(VLAN))} == {10, 20, 30, 99}
    db.close()


def test_errori_dell_import(session_factory):
    db = session_factory()
    run = netbox.execute_import(db, queue(db), lambda url, token, tls: FakeNetBox(url, token, tls, version="3.1.0"))
    assert run.status == "failed" and "Import non eseguito: NetBox 3.1.0 è troppo vecchio" in run.log
    assert run.token_enc is None and run.finished_at is not None

    run = netbox.execute_import(db, queue(db, site_ids=[1, 7]), FakeNetBox)
    assert run.status == "failed" and "Sedi non trovate in NetBox: 7" in run.log
    assert counts(db, Device) == 0

    class Broken(FakeNetBox):
        def get(self, path, params=None):
            if path == "dcim/cables":
                raise RuntimeError("guasto")
            return super().get(path, params)

    run = netbox.execute_import(db, queue(db), Broken)
    assert run.status == "failed" and "Errore inatteso: guasto" in run.log and counts(db, Device) == 0

    stuck = db.get(ImportRun, queue(db))
    stuck.status = "running"
    db.commit()
    assert netbox.recover_interrupted(db) == 1
    assert stuck.status == "failed" and stuck.token_enc is None and "Interrotto: il worker è stato riavviato" in stuck.log
    db.close()


def test_api(client, anonymous, session_factory, monkeypatch):
    monkeypatch.setattr(netbox, "Client", FakeNetBox)
    connection = {"url": "http://netbox.prova.lan/", "token": TOKEN, "verify_tls": False}
    probe = client.post("/api/netbox/test", json=connection)
    assert probe.status_code == 200, probe.text
    assert probe.json() == {
        "version": "4.2.1",
        "counts": {"devices": 5, "interfaces": 12, "cables": 4, "vlans": 4, "prefixes": 3, "ip_addresses": 6, "sites": 2},
        "sites": [{"id": 1, "name": "Milano", "devices": 4}, {"id": 2, "name": "Roma", "devices": 1}],
    }
    monkeypatch.setattr(netbox, "Client", lambda url, token, tls: FakeNetBox(url, token, tls, version="2.11"))
    assert client.post("/api/netbox/test", json=connection).json()["detail"] == (
        "NetBox 2.11 è troppo vecchio: serve la versione 3.3 o successiva")

    assert client.post("/api/netbox/imports", json={**connection, "url": "netbox"}).status_code == 422
    created = client.post("/api/netbox/imports", json={**connection, "site_ids": [2, 1, 2]})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "queued" and body["dry_run"] is True and body["site_ids"] == [1, 2]
    assert body["url"] == "http://netbox.prova.lan" and body["requested_by"] == "admin"
    assert TOKEN not in created.text and "token" not in body
    with session_factory() as db:
        assert decrypt(db.get(ImportRun, body["id"]).token_enc) == TOKEN
    busy = client.post("/api/netbox/imports", json=connection)
    assert busy.status_code == 409 and "in corso" in busy.json()["detail"]
    assert [r["id"] for r in client.get("/api/netbox/imports").json()] == [body["id"]]
    assert client.get(f"/api/netbox/imports/{body['id']}").json()["log"] == ""
    assert client.get("/api/netbox/imports/999").status_code == 404

    # Il worker lo esegue con il suo client; lo storico ricorda chi l'ha chiesto
    with session_factory() as db:
        assert netbox.claim_next(db) == body["id"]
        assert netbox.claim_next(db) is None
        netbox.execute_import(db, body["id"], FakeNetBox)
    done = client.get(f"/api/netbox/imports/{body['id']}").json()
    assert done["status"] == "done" and done["site_names"] == ["Milano", "Roma"]

    # Solo gli amministratori
    create(client, "/users", {"username": "tecnico", "password": "tecnico-123", "role": "editor"})
    anonymous.post("/api/auth/login", json={"username": "tecnico", "password": "tecnico-123"})
    assert anonymous.get("/api/netbox/imports").status_code == 403
    assert anonymous.post("/api/netbox/test", json=connection).status_code == 403
    assert anonymous.post("/api/netbox/imports", json=connection).status_code == 403


def test_tiene_gli_ultimi_import(session_factory):
    db = session_factory()
    for _ in range(netbox.KEEP_RUNS + 3):
        db.add(ImportRun(url="http://nb", status="done"))
    db.flush()
    netbox.prune(db)
    db.commit()
    assert counts(db, ImportRun) == netbox.KEEP_RUNS
    assert db.scalar(select(func.min(ImportRun.id))) == 4
    db.close()
