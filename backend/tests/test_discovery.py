"""Fase 3: profili, job, coda, confronto con il database e approvazione delle modifiche.
La lettura SNMP è sostituita da dati finti (tests/snmp_devices.py): qui si prova tutto il resto."""
import copy
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.secrets import decrypt
from app.discovery.runner import (
    claim_next_run,
    execute_run,
    now,
    recover_interrupted,
    schedule_due_jobs,
)
from app.discovery.targets import TargetError, expand_targets
from app.models import DiscoveryRun, SnmpProfile
from tests.snmp_devices import SW1, SW2, host_data

SW1_HOST, SW2_HOST = "10.99.0.1", "10.99.0.2"


def create(client, path, payload):
    response = client.post(f"/api{path}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture()
def setup(client):
    site = create(client, "/sites", {"name": "Laboratorio"})
    profile = create(client, "/snmp-profiles", {"name": "Lab v2c", "community": "public"})
    job = create(client, "/discovery-jobs", {
        "name": "Lab", "targets": ["10.99.0.0/29"], "profile_ids": [profile["id"]], "site_id": site["id"],
    })
    return {"site": site, "profile": profile, "job": job}


def scan(client, session_factory, job_id, *devices):
    """Mette in coda una scansione e la esegue subito con i device finti indicati."""
    response = client.post(f"/api/discovery-jobs/{job_id}/run")
    assert response.status_code == 202, response.text
    fake = [host_data(device, host, 1, "Lab v2c") for device, host in devices]
    with session_factory() as db:
        run = execute_run(db, response.json()["id"], collector=lambda hosts, creds: fake)
        assert run.status == "done", run.log
        return {"proposed": run.changes_proposed, "applied": run.changes_applied, "log": run.log}


def pending(client, **params):
    return client.get("/api/discovery-changes", params=params).json()["items"]


def approve_all(client):
    ids = [c["id"] for c in pending(client)]
    result = client.post("/api/discovery-changes/approve", json={"ids": ids}).json()
    assert result["failed"] == [], result
    return result


def device_named(client, name):
    return next((d for d in client.get("/api/devices", params={"q": name}).json()["items"] if d["name"] == name), None)


def ports_of(client, device_id):
    return {p["name"]: p for p in client.get(f"/api/devices/{device_id}/ports").json()}


# ---------------------------------------------------------------- intervalli
def test_intervalli_da_scansionare():
    assert expand_targets(["10.0.0.0/30", "10.0.0.2", "10.0.1.1-3", "10.0.2.5-10.0.2.6"], 100) == [
        "10.0.0.1", "10.0.0.2", "10.0.1.1", "10.0.1.2", "10.0.1.3", "10.0.2.5", "10.0.2.6",
    ]
    with pytest.raises(TargetError):
        expand_targets(["10.0.0.0/16"], 4096)
    with pytest.raises(TargetError):
        expand_targets(["10.0.0.300"], 10)


# ---------------------------------------------------------------- profili e job via API
def test_profili_segreti_cifrati_e_mai_restituiti(client, session_factory):
    assert client.post("/api/snmp-profiles", json={"name": "senza community"}).status_code == 422
    profile = create(client, "/snmp-profiles", {"name": "v2c", "community": "s3greta"})
    assert profile["has_community"] is True and "community" not in profile and "community_enc" not in profile

    with session_factory() as db:
        stored = db.get(SnmpProfile, profile["id"]).community_enc
    assert "s3greta" not in stored and decrypt(stored) == "s3greta"

    # Modificare altri campi non tocca la community
    updated = client.patch(f"/api/snmp-profiles/{profile['id']}", json={"description": "core"}).json()
    assert updated["has_community"] is True

    bad_v3 = {"name": "v3", "version": "v3", "username": "netmap", "priv_protocol": "aes", "priv_key": "privkey123"}
    assert client.post("/api/snmp-profiles", json=bad_v3).status_code == 422  # privacy senza autenticazione
    v3 = create(client, "/snmp-profiles", {**bad_v3, "auth_protocol": "sha", "auth_key": "authkey123"})
    assert v3["has_auth_key"] and v3["has_priv_key"]
    assert client.post("/api/snmp-profiles", json={**bad_v3, "name": "corta", "auth_protocol": "sha", "auth_key": "corta"}).status_code == 422


def test_job_validazione_e_coda(client, setup):
    base = {"name": "x", "profile_ids": [setup["profile"]["id"]], "site_id": setup["site"]["id"]}
    assert client.post("/api/discovery-jobs", json={**base, "targets": ["10.0.0.999"]}).status_code == 422
    assert client.post("/api/discovery-jobs", json={**base, "targets": ["10.0.0.0/8"]}).status_code == 422
    assert client.post("/api/discovery-jobs", json={**base, "targets": ["10.0.0.1"], "profile_ids": [999]}).status_code == 422
    assert setup["job"]["targets"] == ["10.99.0.0/29"]

    job_id = setup["job"]["id"]
    assert client.post(f"/api/discovery-jobs/{job_id}/run").status_code == 202
    assert client.post(f"/api/discovery-jobs/{job_id}/run").status_code == 409  # già in coda
    runs = client.get("/api/discovery-runs", params={"job_id": job_id}).json()
    assert runs["total"] == 1 and runs["items"][0]["status"] == "queued"


def test_pianificazione_e_worker(client, setup, session_factory):
    job_id = setup["job"]["id"]
    client.patch(f"/api/discovery-jobs/{job_id}", json={"interval_hours": 6})
    with session_factory() as db:
        assert schedule_due_jobs(db) == 1   # mai eseguito: parte subito
        assert schedule_due_jobs(db) == 0   # già in coda
        run_id = claim_next_run(db)
        assert run_id is not None and claim_next_run(db) is None
        assert recover_interrupted(db) == 1  # il worker riparte: quella in corso è interrotta
        assert db.get(DiscoveryRun, run_id).status == "failed"
        assert schedule_due_jobs(db) == 0   # eseguito da poco
        assert schedule_due_jobs(db, now() + timedelta(hours=7)) == 1


# ---------------------------------------------------------------- flusso completo
def test_device_nuovi_poi_cavo_poi_niente(client, setup, session_factory):
    job_id = setup["job"]["id"]

    # 1) Due device sconosciuti: si propone di crearli, niente viene scritto da solo
    result = scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    assert result == {**result, "proposed": 2, "applied": 0}
    changes = pending(client)
    assert {(c["object_type"], c["action"], c["device_label"]) for c in changes} == {
        ("device", "create", "sw-sim-01"), ("device", "create", "sw-sim-02"),
    }
    assert client.get("/api/devices").json()["total"] == 0
    assert client.get("/api/discovery-changes/count").json() == {"pending": 2}

    approve_all(client)
    sw1, sw2 = device_named(client, "sw-sim-01"), device_named(client, "sw-sim-02")
    assert sw1["source"] == "snmp" and sw1["serial"] == "FOCSIM0001" and sw1["site_id"] == setup["site"]["id"]
    assert sw1["sys_name"] == "sw-sim-01.lab.local" and sw1["last_seen_at"]
    model = client.get(f"/api/device-types/{sw1['device_type_id']}").json()
    assert model["model"] == "C9300-48P" and model["sys_object_id"] == "1.3.6.1.4.1.9.1.2494"
    assert client.get(f"/api/manufacturers/{model['manufacturer_id']}").json()["name"] == "Cisco"

    ports = ports_of(client, sw1["id"])
    assert set(ports) == {"Gi1/0/1", "Gi1/0/2", "Te1/1/1", "Vl99", "Po1"}
    assert ports["Po1"]["type"] == "lag" and ports["Vl99"]["type"] == "virtual"
    assert ports["Gi1/0/2"]["enabled"] is False and ports["Te1/1/1"]["oper_status"] == "up"
    assert [ip["address"] for ip in ports["Vl99"]["ips"]] == ["10.99.0.1/24", "fd00::1/64"]
    assert ports["Vl99"]["ips"][0]["is_primary"] is True

    # 2) Ora entrambi i device esistono: LLDP visto dai due lati diventa un solo cavo da approvare
    result = scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    changes = pending(client)
    assert [(c["object_type"], c["action"]) for c in changes] == [("cable", "create")], changes
    assert "sw-sim-01 Te1/1/1 ↔ sw-sim-02 49" in changes[0]["summary"]
    approve_all(client)
    cable = client.get("/api/cables").json()["items"][0]
    assert {cable["a_device_name"], cable["b_device_name"]} == {"sw-sim-01", "sw-sim-02"} and cable["source"] == "snmp"

    # 3) Tutto allineato: nessuna modifica
    result = scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    assert result["proposed"] == 0 and result["applied"] == 0 and pending(client) == []


def test_device_inserito_a_mano(client, setup, session_factory):
    """Device manuale riconosciuto dal seriale: i suoi campi si propongono, le porte nuove entrano da sole."""
    site_id, job_id = setup["site"]["id"], setup["job"]["id"]
    client.patch(f"/api/discovery-jobs/{job_id}", json={"auto_new_interfaces": True})
    core = create(client, "/devices", {"name": "core", "site_id": site_id, "serial": "focsim0001"})
    create(client, "/interfaces", {"device_id": core["id"], "name": "GigabitEthernet1/0/1", "speed_mbps": 100})

    result = scan(client, session_factory, job_id, (SW1, SW1_HOST))
    assert result["applied"] == 4  # Gi1/0/2, Te1/1/1, Vl99, Po1
    device = client.get(f"/api/devices/{core['id']}").json()
    assert device["name"] == "core" and device["sys_name"] == "sw-sim-01.lab.local"  # il nome non si tocca

    changes = {(c["object_type"], c["action"]): c for c in pending(client)}
    assert set(changes) == {("device", "update"), ("interface", "update")}
    port_change = changes[("interface", "update")]
    assert port_change["diff"]["Velocità (Mbps)"] == [100, 1000]
    assert port_change["diff"]["Descrizione"] == [None, "Uplink firewall"]
    assert "Nome" not in port_change["diff"]  # GigabitEthernet1/0/1 = Gi1/0/1
    assert changes[("device", "update")]["diff"]["Modello"][0] is None

    # Le porte create dalla scansione ora esistono: alla prossima si propongono gli IP (non automatici nel job)
    scan(client, session_factory, job_id, (SW1, SW1_HOST))
    ips = [c for c in pending(client) if c["object_type"] == "ip"]
    assert sorted(c["data"]["address"] for c in ips) == ["10.99.0.1/24", "fd00::1/64"]
    assert next(c for c in ips if c["data"]["address"] == "10.99.0.1/24")["data"]["is_primary"] is True


def test_rifiuto_porta_sparita_e_pulizia(client, setup, session_factory):
    job_id = setup["job"]["id"]
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    sw2_change = next(c for c in pending(client) if c["device_label"] == "sw-sim-02")
    client.post("/api/discovery-changes/reject", json={"ids": [sw2_change["id"]]})
    approve_all(client)  # solo sw-sim-01

    # Rifiutata con gli stessi dati: non torna
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    assert all(c["device_label"] != "sw-sim-02" for c in pending(client))

    # Una porta sparisce: si propone di eliminarla, non la si elimina da soli
    without_port = copy.deepcopy(SW1)
    del without_port["interfaces"][2]
    scan(client, session_factory, job_id, (without_port, SW1_HOST))
    stale = [c for c in pending(client) if c["action"] == "stale"]
    assert len(stale) == 1 and "Gi1/0/2" in stale[0]["summary"]
    sw1 = device_named(client, "sw-sim-01")
    assert "Gi1/0/2" in ports_of(client, sw1["id"])

    # La porta ricompare: la proposta non serve più e sparisce
    scan(client, session_factory, job_id, (SW1, SW1_HOST))
    assert [c for c in pending(client) if c["action"] == "stale"] == []

    # Se invece la si approva, la porta viene eliminata
    scan(client, session_factory, job_id, (without_port, SW1_HOST))
    approve_all(client)
    assert "Gi1/0/2" not in ports_of(client, sw1["id"])


def test_cavo_diverso_e_approvazione_non_piu_valida(client, setup, session_factory):
    job_id = setup["job"]["id"]
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    approve_all(client)
    sw1, sw2 = device_named(client, "sw-sim-01"), device_named(client, "sw-sim-02")
    p1, p2 = ports_of(client, sw1["id"]), ports_of(client, sw2["id"])

    # A mano Te1/1/1 è collegata alla porta 1, ma LLDP dice porta 49
    create(client, "/cables", {"a_interface_id": p1["Te1/1/1"]["id"], "b_interface_id": p2["1"]["id"]})
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    [change] = pending(client)
    assert change["action"] == "update" and change["diff"]["Collegamento"][0] == "sw-sim-01 Te1/1/1 ↔ sw-sim-02 1"
    approve_all(client)
    cables = client.get("/api/cables").json()["items"]
    assert len(cables) == 1 and {cables[0]["a_interface_name"], cables[0]["b_interface_name"]} == {"Te1/1/1", "49"}

    # Proposta superata dai fatti: la porta è stata occupata nel frattempo -> errore leggibile, niente danni
    client.delete(f"/api/cables/{cables[0]['id']}")
    scan(client, session_factory, job_id, (SW1, SW1_HOST), (SW2, SW2_HOST))
    [change] = pending(client)
    create(client, "/cables", {"a_interface_id": p2["49"]["id"], "b_interface_id": p2["2"]["id"]})
    result = client.post("/api/discovery-changes/approve", json={"ids": [change["id"]]}).json()
    assert result["applied"] == 0 and "già un cavo" in result["failed"][0]["error"]
    assert client.get("/api/discovery-changes", params={"status": "failed"}).json()["total"] == 1


def test_porte_nuove_automatiche_ma_ip_da_approvare(client, setup, session_factory):
    """Un'applicazione automatica che fallisce resta in attesa con l'errore, non si perde."""
    job_id = setup["job"]["id"]
    scan(client, session_factory, job_id, (SW1, SW1_HOST))
    approve_all(client)
    sw1 = device_named(client, "sw-sim-01")
    client.patch(f"/api/discovery-jobs/{job_id}", json={"auto_new_interfaces": True})

    bigger = copy.deepcopy(SW1)
    bigger["interfaces"][3] = ("Gi1/0/3", "GigabitEthernet1/0/3", 6, 1500, 1000, "00:11:22:33:44:03", 1, 1, "")
    result = scan(client, session_factory, job_id, (bigger, SW1_HOST))
    assert result["applied"] == 1 and "Gi1/0/3" in ports_of(client, sw1["id"])
    applied = client.get("/api/discovery-changes", params={"status": "applied"}).json()["items"]
    assert any(c["auto"] and "Gi1/0/3" in c["summary"] for c in applied)
