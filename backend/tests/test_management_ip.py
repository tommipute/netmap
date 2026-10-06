"""IP di management: campo nel modulo del device e uno solo per device."""
from tests.test_api import create


def ips_of(client, device_id):
    ports = client.get(f"/api/devices/{device_id}/ports").json()
    return {ip["address"]: (p["name"], ip["is_primary"]) for p in ports for ip in p["ips"]}


def test_campo_ip_di_management_nel_device(client):
    site = create(client, "/sites", {"name": "Sede"})
    sw = create(client, "/devices", {"name": "sw", "site_id": site["id"], "management_ip": "10.10.99.55/24"})
    assert sw["management_ip"] == "10.10.99.55/24"
    # Senza porte la crea: "mgmt", solo management
    ports = client.get(f"/api/devices/{sw['id']}/ports").json()
    assert [(p["name"], p["mgmt_only"]) for p in ports] == [("mgmt", True)]
    assert client.get(f"/api/interfaces/{ports[0]['id']}").json()["device_management_ip"] == "10.10.99.55/24"

    # Cambiato: il nuovo va sulla stessa porta, il vecchio resta ma non è più di management
    sw = client.patch(f"/api/devices/{sw['id']}", json={"management_ip": "10.10.99.56/24"}).json()
    assert sw["management_ip"] == "10.10.99.56/24"
    assert ips_of(client, sw["id"]) == {"10.10.99.55/24": ("mgmt", False), "10.10.99.56/24": ("mgmt", True)}

    # Salvare il device senza toccare il campo non crea doppioni; vuoto = nessun IP di management
    client.patch(f"/api/devices/{sw['id']}", json={"name": "sw-01", "management_ip": "10.10.99.56/24"})
    assert len(ips_of(client, sw["id"])) == 2
    assert client.patch(f"/api/devices/{sw['id']}", json={"management_ip": None}).json()["management_ip"] is None
    assert ips_of(client, sw["id"])["10.10.99.56/24"] == ("mgmt", False)


def test_usa_la_porta_esistente_e_rifiuta_ip_di_altri(client):
    site = create(client, "/sites", {"name": "Sede"})
    sw = create(client, "/devices", {"name": "sw", "site_id": site["id"]})
    svi = create(client, "/interfaces", {"device_id": sw["id"], "name": "Vlan99", "type": "virtual"})
    create(client, "/ip-addresses", {"address": "10.10.99.1/24", "interface_id": svi["id"], "is_primary": True})
    # Un nuovo IP di management va dove sta quello attuale (la SVI), senza creare "mgmt"
    client.patch(f"/api/devices/{sw['id']}", json={"management_ip": "10.10.99.2/24"})
    assert ips_of(client, sw["id"])["10.10.99.2/24"] == ("Vlan99", True)

    other = create(client, "/devices", {"name": "altro", "site_id": site["id"], "management_ip": "10.10.99.9/24"})
    res = client.patch(f"/api/devices/{sw['id']}", json={"management_ip": "10.10.99.9/24"})
    assert res.status_code == 422 and "altro" in res.json()["detail"]
    assert client.get(f"/api/devices/{other['id']}").json()["management_ip"] == "10.10.99.9/24"


def test_un_solo_ip_di_management_per_device(client):
    site = create(client, "/sites", {"name": "Sede"})
    sw = create(client, "/devices", {"name": "sw", "site_id": site["id"], "management_ip": "10.10.99.55/24"})
    port = create(client, "/interfaces", {"device_id": sw["id"], "name": "Gi1/0/1"})
    # Un secondo IP con il flag viene rifiutato, senza toglierlo di nascosto al primo
    res = client.post("/api/ip-addresses", json={"address": "10.10.20.1/24", "interface_id": port["id"], "is_primary": True})
    assert res.status_code == 422 and "10.10.99.55/24" in res.json()["detail"]
    ip = create(client, "/ip-addresses", {"address": "10.10.20.1/24", "interface_id": port["id"]})
    assert client.patch(f"/api/ip-addresses/{ip['id']}", json={"is_primary": True}).status_code == 422
    assert client.get(f"/api/devices/{sw['id']}").json()["management_ip"] == "10.10.99.55/24"
