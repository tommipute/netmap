"""Ruolo predefinito del modello e ruolo indovinato dalla scansione."""
from app.services.roles import guess_role
from tests.test_api import create
from tests.test_discovery import SW1, SW1_HOST, approve_all, device_named, scan, setup  # noqa: F401


def test_ruolo_predefinito_del_modello(client):
    site = create(client, "/sites", {"name": "Sede"})
    vendor = create(client, "/manufacturers", {"name": "Fortinet"})
    firewall = create(client, "/device-roles", {"name": "Firewall", "level": 0})
    model = create(client, "/device-types", {"manufacturer_id": vendor["id"], "model": "FortiGate 100F"})
    old = create(client, "/devices", {"name": "fw-vecchio", "site_id": site["id"], "device_type_id": model["id"]})
    assert old["role_id"] is None

    # Impostato sul modello: lo prendono i device esistenti senza ruolo (e nello storico risulta)
    client.patch(f"/api/device-types/{model['id']}", json={"default_role_id": firewall["id"]})
    assert client.get(f"/api/devices/{old['id']}").json()["role_id"] == firewall["id"]
    # ...e quelli nuovi; un ruolo scelto a mano vince
    new = create(client, "/devices", {"name": "fw-nuovo", "site_id": site["id"], "device_type_id": model["id"]})
    assert new["role_id"] == firewall["id"]
    other = create(client, "/device-roles", {"name": "Core"})
    chosen = create(client, "/devices", {"name": "fw-3", "site_id": site["id"], "device_type_id": model["id"], "role_id": other["id"]})
    assert chosen["role_id"] == other["id"]
    # Togliere il ruolo a un device non lo fa ricomparire salvando di nuovo
    client.patch(f"/api/devices/{new['id']}", json={"role_id": None, "device_type_id": model["id"]})
    assert client.get(f"/api/devices/{new['id']}").json()["role_id"] is None


def test_ruolo_indovinato_dalla_scansione(client, setup, session_factory):
    switch = create(client, "/device-roles", {"name": "Switch di accesso"})
    create(client, "/device-roles", {"name": "Firewall"})
    scan(client, session_factory, setup["job"]["id"], (SW1, SW1_HOST))  # Catalyst: è uno switch
    approve_all(client)
    sw1 = device_named(client, "sw-sim-01")
    assert sw1["role_id"] == switch["id"]
    assert client.get(f"/api/device-types/{sw1['device_type_id']}").json()["default_role_id"] == switch["id"]


def test_indovina(session_factory):
    from app.models import DeviceRole
    with session_factory() as db:
        db.add_all([DeviceRole(name="Firewall"), DeviceRole(name="Access point"), DeviceRole(name="Switch")])
        db.flush()
        assert guess_role(db, "FortiGate-100F v7.2.8").name == "Firewall"
        assert guess_role(db, "Cisco AIR-AP2802I").name == "Access point"
        assert guess_role(db, "HP J9776A 2930F-24G Switch").name == "Switch"
        assert guess_role(db, "Linux server 5.15") is None


def test_tipo_riconosciuto():
    from app.services.roles import detect_kind

    def kind(**signals):
        found = detect_kind(**signals)
        return (found.kind.key, found.reason) if found else None

    # MIB standard prima di tutto: una stampante HP dice solo "HP ETHERNET MULTI-ENVIRONMENT"
    assert kind(sys_descr="HP ETHERNET MULTI-ENVIRONMENT", mibs=["printer"]) == ("printer", "Printer-MIB")
    assert kind(sys_descr="Network Management Card AOS v6.8", mibs=["ups"]) == ("ups", "UPS-MIB")
    # Parole della descrizione o del modello
    assert kind(sys_descr="Brother NC-8300h, Firmware Ver.1.11") == ("printer", "descrizione SNMP")
    assert kind(sys_descr="APC Web/SNMP Management Card (MB:v4.1.0 PF:v6.4.6) Smart-UPS 1500")[0] == "ups"
    assert kind(sys_descr="APC Rack PDU AP8853")[0] == "pdu"
    assert kind(sys_descr="Linux DiskStation 4.4.302+")[0] == "nas"
    assert kind(sys_descr="AXIS P3245-V Network Camera")[0] == "camera"
    assert kind(sys_descr="Yealink SIP-T46U")[0] == "phone"
    assert kind(sys_descr="Cisco Controller", model="AIR-CT3504-K9")[0] == "wlc"
    assert kind(sys_descr="FortiGate-60F v7.2.5")[0] == "firewall"
    assert kind(sys_descr="Cisco IOS Software, ISR4300 Software")[0] == "router"
    assert kind(sys_descr="HP J9776A 2930F-24G Switch")[0] == "switch"
    assert kind(sys_descr="VMware ESXi 8.0.2")[0] == "server"
    # Produttore che fa un solo tipo di apparato (Synology), poi capacità LLDP e sysServices
    assert kind(sys_descr="Linux nas01", sys_object_id="1.3.6.1.4.1.6574.1") == ("nas", "produttore")
    assert kind(sys_descr="Linux ap", caps=["wlanAccessPoint", "station"]) == ("ap", "LLDP")
    assert kind(sys_descr="", caps=["bridge", "router"]) == ("switch", "LLDP")
    assert kind(sys_descr="Linux", sys_services=6) == ("switch", "sysServices")
    assert kind(sys_descr="Linux", sys_services=4) == ("router", "sysServices")
    assert kind(sys_descr="Linux server 5.15", sys_services=72) is None  # un host qualsiasi: non si sa


def test_scansione_propone_il_ruolo_nuovo(client, setup, session_factory):
    import copy

    printer = copy.deepcopy(SW1)
    printer["system"] = {"descr": "HP ETHERNET MULTI-ENVIRONMENT,ROM none,JETDIRECT,JD153", "printer": True,
                         "object_id": "1.3.6.1.4.1.11.2.3.9.1", "name": "stampante-1", "location": "Piano 1"}
    printer["entities"] = {1: (3, "CNB1234567", "HP LaserJet M507")}
    scan(client, session_factory, setup["job"]["id"], (printer, "10.99.0.3"))
    change = next(c for c in client.get("/api/discovery-changes").json()["items"] if c["device_label"] == "stampante-1")
    details = {name: new for name, _old, new in change["diff"]}
    assert details["Ruolo"] == "Stampante (nuovo)" and details["Tipo riconosciuto"] == "Stampante (Printer-MIB)"
    assert "role" not in change["data"]["device_type"] and change["data"]["device_type"]["create"]["kind"] == "printer"
    approve_all(client)
    device = device_named(client, "stampante-1")
    role = client.get(f"/api/device-roles/{device['role_id']}").json()
    assert role["name"] == "Stampante" and role["level"] == 4
    # Il ruolo nuovo ora esiste: la stessa scansione non propone niente di nuovo sul device
    assert client.get("/api/device-roles", params={"q": "Stampante"}).json()["total"] == 1
