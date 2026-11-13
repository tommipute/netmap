"""Regole SNMP: controlli, export e import, prova su un indirizzo, effetto sulla scansione."""
from types import SimpleNamespace

from app.discovery import snmp, snmp_rules
from app.discovery.runner import execute_run
from tests.snmp_devices import SW2, host_data
from tests.test_discovery import pending, setup  # noqa: F401

HP = {"name": "HP senza modello", "match_object_id": "1.3.6.1.4.1.11"}


def rule(id=1, **fields):
    base = dict(name=f"r{id}", match_object_id=None, match_descr=None, model_oid=None, model_regex=None,
                serial_oid=None, port_name=None, ignore_ports=None, ignore_if_types=[], manufacturer=None, kind=None)
    return snmp_rules.compile_rule(SimpleNamespace(**{**base, **fields}, id=id))


def test_quale_regola_vince():
    generic = rule(1, match_object_id="1.3.6.1.4.1.11", model_regex=r"(J\d{4}A)", serial_oid="1.3.6.1.4.1.11.9")
    precise = rule(2, match_object_id="1.3.6.1.4.1.11.2.3.7", model_regex=r"(\d{4}-48G)")
    by_descr = rule(3, match_descr="revision WB", kind="ap")
    other = rule(4, match_object_id="1.3.6.1.4.1.110")  # 110 non è 11
    sys_object_id, sys_descr = SW2["system"]["object_id"], SW2["system"]["descr"]
    matched = snmp_rules.matching([generic, precise, by_descr, other], sys_object_id, sys_descr)
    assert [r.name for r in matched] == ["r2", "r1", "r3"]

    hd = host_data(SW2, "10.99.0.2")
    snmp_rules.apply(hd, matched, {"1.3.6.1.4.1.11.9": b"SERIALE-OID "})
    # ogni cosa dalla regola più precisa che la imposta
    assert (hd.model, hd.model_source, hd.serial, hd.kind) == ("2920-48G", "rule", "SERIALE-OID", "ap")
    assert hd.rules == ["r2", "r1", "r3"]
    assert not rule(5).matches(sys_object_id, sys_descr)  # senza criteri non vale per niente


def test_porte_ignorate_tranne_quella_con_l_ip():
    hd = host_data(SW2, "10.99.0.2")
    snmp_rules.apply(hd, [rule(ignore_ports="^(1|VLAN.*)$", ignore_if_types=[6])], {})
    # 1 ignorata per nome, 2 e 49 per tipo; VLAN99 ha l'IP di management e resta
    assert [i.name for i in hd.interfaces] == ["VLAN99"]
    assert hd.fdb == [] and hd.neighbors == [] and hd.port_vlans == {} and hd.notes["ports_ignored"] == 3


def test_controlli_della_regola(client):
    def post(**fields):
        return client.post("/api/snmp-rules", json=fields)

    assert "a quali apparati" in post(name="vuota", model_regex="x").json()["detail"]
    assert post(name="regex", match_descr="(").status_code == 422
    assert post(name="oid", match_object_id="1.3.6.x").status_code == 422
    assert post(name="tipo", match_descr="x", kind="frigorifero").status_code == 422
    assert post(name="porte", match_descr="x", port_name="ifName").status_code == 422
    saved = post(name="TP-Link", match_object_id=" .1.3.6.1.4.1.11863. ", port_name="descr", kind="switch").json()
    assert saved["match_object_id"] == "1.3.6.1.4.1.11863" and saved["enabled"] is True
    # In modifica il controllo guarda la regola intera
    response = client.patch(f"/api/snmp-rules/{saved['id']}", json={"match_object_id": None})
    assert response.status_code == 422


def test_export_e_import(client):
    first = client.post("/api/snmp-rules", json={**HP, "model_regex": r"(J\d+A)"}).json()
    client.post("/api/snmp-rules", json={"name": "Zyxel", "match_descr": "^GS1900", "enabled": False})
    exported = client.get("/api/snmp-rules/export").json()
    assert exported["netmap"] == "snmp-rules" and exported["version"] == 1
    assert [r["name"] for r in exported["rules"]] == ["HP senza modello", "Zyxel"]
    assert "id" not in exported["rules"][0]

    # Stesso nome (anche con maiuscole diverse) = aggiornata, nome nuovo = aggiunta
    changed = {**exported["rules"][0], "name": "hp SENZA modello", "serial_oid": "1.3.6.1.4.1.11.2.36.1.1.2.9.0"}
    new = {"name": "MikroTik", "match_object_id": "1.3.6.1.4.1.14988", "kind": "router"}
    result = client.post("/api/snmp-rules/import", json={"rules": [changed, new]}).json()
    assert result == {"created": 1, "updated": 1}
    rules = {r["name"]: r for r in client.get("/api/snmp-rules").json()["items"]}
    assert set(rules) == {"hp SENZA modello", "Zyxel", "MikroTik"}
    assert rules["hp SENZA modello"]["id"] == first["id"] and rules["hp SENZA modello"]["serial_oid"].endswith(".9.0")

    # Un file con una regola sbagliata non cambia niente
    bad = client.post("/api/snmp-rules/import", json={"rules": [{**new, "kind": "switch"}, {"name": "x"}]})
    assert bad.status_code == 422 and "Regola «x»" in bad.json()["detail"]
    double = client.post("/api/snmp-rules/import", json={"rules": [new, new]})
    assert double.status_code == 422
    assert client.get("/api/snmp-rules", params={"q": "MikroTik"}).json()["items"][0]["kind"] == "router"
    # Campi sconosciuti (es. un file di una versione più nuova) rifiutati, non persi in silenzio
    assert client.post("/api/snmp-rules/import", json={"rules": [{**new, "lldp_port": "x"}]}).status_code == 422


def test_prova_di_una_regola(client, setup, monkeypatch):
    client.post("/api/snmp-rules", json={**HP, "manufacturer": "Hewlett Packard"})  # salvata: vale prima e dopo
    calls = []

    def fake_probe(hosts, creds, concurrency=50, ping=True, rules=(), apply_rules=True):
        calls.append((hosts, [r.name for r in rules], apply_rules))
        if hosts == ["10.99.0.9"]:
            return [snmp.HostProbe("10.99.0.9", attempts=[snmp.Attempt("Lab v2c", "nessuna risposta")])]
        hd = host_data(SW2, "10.99.0.2", 1, "Lab v2c")
        hd.rule_values = {"1.3.6.1.4.1.11.9.0": b"SERIALE"}
        return [snmp.HostProbe("10.99.0.2", data=hd)]

    monkeypatch.setattr(snmp, "probe_all", fake_probe)
    draft = {"name": "bozza", "match_descr": "2920", "serial_oid": "1.3.6.1.4.1.11.9.0", "port_name": "alias"}
    body = {"host": "10.99.0.2", "profile_ids": [setup["profile"]["id"]], "rule": draft}
    result = client.post("/api/snmp-rules/test", json=body).json()
    assert calls == [(["10.99.0.2"], ["HP senza modello", "bozza"], False)]
    assert result["matches"] is True
    before, after = result["before"], result["after"]
    assert before["manufacturer"] == after["manufacturer"] == "Hewlett Packard"
    assert before["rules"] == ["HP senza modello"] and after["rules"] == ["HP senza modello", "bozza"]
    assert (before["serial"], after["serial"]) == ("SGSIM0002", "SERIALE")
    assert result["ports"] == [{"if_index": 49, "before": "49", "after": "uplink core"}]  # solo quelle che cambiano
    assert pending(client) == []  # non salva niente

    # La regola in modifica conta solo com'è nel modulo
    saved = client.get("/api/snmp-rules").json()["items"][0]
    calls.clear()
    client.post("/api/snmp-rules/test", json={**body, "rule_id": saved["id"], "rule": {**HP, "kind": "ap"}})
    assert calls[0][1] == ["HP senza modello"]

    assert client.post("/api/snmp-rules/test", json={**body, "rule": {"name": "x"}}).status_code == 422
    assert client.post("/api/snmp-rules/test", json={**body, "host": "10.0.0.0/24"}).status_code == 422
    silent = client.post("/api/snmp-rules/test", json={**body, "host": "10.99.0.9"}).json()
    assert silent["before"] is None and silent["attempts"][0]["error"] == "nessuna risposta"


def test_scansione_con_produttore_e_tipo_della_regola(client, setup, session_factory):
    """Produttore e tipo di una regola valgono per il modello nuovo proposto e si vedono nel resoconto."""
    hd = host_data(SW2, "10.99.0.2", 1, "Lab v2c")
    snmp_rules.apply(hd, [rule(name="Mio HP", match_object_id="1.3.6.1.4.1.11", manufacturer="Acme", kind="ap")], {})
    run = client.post(f"/api/discovery-jobs/{setup['job']['id']}/run").json()
    with session_factory() as db:
        assert execute_run(db, run["id"], collector=lambda hosts, creds: [hd]).status == "done"
    [change] = [c for c in pending(client) if c["object_type"] == "device"]
    device_type = change["data"]["device_type"]
    assert device_type["create"]["manufacturer"] == "Acme" and device_type["create"]["kind"] == "ap"
    assert ["Tipo riconosciuto", None, "Access point (regola SNMP)"] in change["diff"]

    from app.models import SnmpReport
    with session_factory() as db:
        report = db.query(SnmpReport).one().data
    assert report["rules"] == ["Mio HP"] and report["kind"] == "ap" and report["kind_reason"] == "regola SNMP"
    assert report["manufacturer"] == "Acme"
