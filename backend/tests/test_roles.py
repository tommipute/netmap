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
