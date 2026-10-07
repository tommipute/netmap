"""Storico delle modifiche: si scrive da solo a ogni salvataggio."""
from app.services.monitor import Probe, check_devices
from tests.test_api import create
from tests.test_discovery import SW2, SW2_HOST, approve_all, device_named, scan, setup  # noqa: F401


def history(client, **params):
    return client.get("/api/audit-log", params=params).json()["items"]


def test_chi_cosa_quando(client):
    site = create(client, "/sites", {"name": "Sede"})
    role = create(client, "/device-roles", {"name": "Switch", "color": "#336699"})
    sw = create(client, "/devices", {"name": "sw-01", "site_id": site["id"]})
    client.patch(f"/api/devices/{sw['id']}", json={"status": "planned", "role_id": role["id"]})

    rows = history(client, device_id=sw["id"])
    assert [(r["action"], r["username"], r["source"]) for r in rows] == [("update", "admin", "utente"), ("create", "admin", "utente")]
    # Il riferimento compare con il nome, non con l'id
    assert sorted(rows[0]["changes"]) == [["Ruolo", None, "Switch"], ["Stato", "active", "planned"]]

    # Un errore (422) non lascia righe nello storico
    before = client.get("/api/audit-log").json()["total"]
    assert client.patch(f"/api/devices/{sw['id']}", json={"rack_position": 999}).status_code == 422
    assert client.get("/api/audit-log").json()["total"] == before


def test_cavo_nello_storico_dei_due_device_ed_eliminazione(client):
    site = create(client, "/sites", {"name": "Sede"})
    a = create(client, "/devices", {"name": "a", "site_id": site["id"]})
    b = create(client, "/devices", {"name": "b", "site_id": site["id"]})
    pa = create(client, "/interfaces", {"device_id": a["id"], "name": "Gi1"})
    pb = create(client, "/interfaces", {"device_id": b["id"], "name": "Gi2"})
    create(client, "/cables", {"a_interface_id": pa["id"], "b_interface_id": pb["id"]})
    for device in (a, b):
        assert ("cable", "create", "a Gi1 ↔ b Gi2") in {(r["object_type"], r["action"], r["label"]) for r in history(client, device_id=device["id"])}
    client.delete(f"/api/devices/{a['id']}")
    deleted = history(client, device_id=a["id"])[0]
    assert (deleted["object_type"], deleted["action"], deleted["label"]) == ("device", "delete", "a")


def test_scansione_e_segreti(client, setup, session_factory):
    scan(client, session_factory, setup["job"]["id"], (SW2, SW2_HOST))
    approve_all(client)
    sw2 = device_named(client, "sw-sim-02")
    rows = history(client, device_id=sw2["id"])
    # Una riga per il device nuovo, non una per ognuna delle sue porte e IP; chi ha approvato resta registrato
    created = [(r["object_type"], r["source"], r["username"]) for r in rows if r["action"] == "create"]
    assert created == [("device", "scansione", "admin")]

    # Il monitor cambia solo lo stato live: niente storico
    before = client.get("/api/audit-log").json()["total"]
    with session_factory() as db:
        check_devices(db, prober=lambda targets: {t.device_id: Probe(reachable=False) for t in targets})
    assert client.get("/api/audit-log").json()["total"] == before

    # I segreti non finiscono mai nello storico
    profile_id = setup["job"]["profile_ids"][0]
    client.patch(f"/api/snmp-profiles/{profile_id}", json={"community": "segretissima"})
    row = history(client, object_type="snmp_profile")[0]
    assert row["changes"] == [["Community", None, "cambiata"]]
    assert "segretissima" not in str(client.get("/api/audit-log").json())
