"""Subnet create dalla scansione dagli IP letti sugli switch (indirizzo con maschera)."""
from tests.test_discovery import (  # noqa: F401  (setup è una fixture)
    SW1_HOST, SW2_HOST, approve_all, pending, scan, setup,
)
from tests.snmp_devices import SW1, SW2


def prefixes(client):
    return {p["prefix"]: p for p in client.get("/api/prefixes").json()["items"]}


def test_subnet_dalla_scansione(client, setup, session_factory):
    job_id, site_id = setup["job"]["id"], setup["site"]["id"]
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    approve_all(client)  # i device: gli IP e le subnet arrivano alla scansione dopo
    assert prefixes(client) == {}
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    # Senza approvazione, e una volta sola anche se la vedono tutti e due gli switch; niente 127.0.0.0/8
    found = prefixes(client)
    assert set(found) == {"10.99.0.0/24", "fd00::/64"}
    assert not [c for c in pending(client) if c["object_type"] == "prefix"]
    # Sede del device, VLAN dell'interfaccia che ha l'IP (Vl99 / VLAN99), IPv6 su una porta senza VID
    vlan = next(v for v in client.get("/api/vlans").json()["items"] if v["vid"] == 99)
    assert (found["10.99.0.0/24"]["site_id"], found["10.99.0.0/24"]["vlan_id"]) == (site_id, vlan["id"])
    assert found["10.99.0.0/24"]["description"] == "Trovata dalla scansione SNMP"

    # Una subnet cancellata a mano non torna; una cambiata a mano non si tocca
    assert client.delete(f"/api/prefixes/{found['fd00::/64']['id']}").status_code == 204
    client.patch(f"/api/prefixes/{found['10.99.0.0/24']['id']}", json={"description": "Laboratorio", "vlan_id": None})
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    found = prefixes(client)
    assert set(found) == {"10.99.0.0/24"}
    assert found["10.99.0.0/24"]["description"] == "Laboratorio"


def test_vlan_dal_nome_dell_interfaccia():
    from app.discovery.planner import _SVI
    names = {"Vl10": 10, "Vlan10": 10, "VLAN 10": 10, "Vlan-interface10": 10, "Vlanif10": 10, "irb.10": 10,
             "vlan10": 10, "Gi1/0/1": None, "Vlan10.5": None, "LoopBack0": None}
    assert {n: int(m.group(1)) if (m := _SVI.match(n)) else None for n in names} == names
