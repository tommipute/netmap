"""Import/export CSV dei device."""
HEADER = "name;status;site;location;rack;rack_position;manufacturer;model;role;primary_ip;serial;asset_tag;description"


def run_import(client, rows, header=HEADER, **options):
    csv_data = "\n".join([header, *rows]) if header else "\n".join(rows)
    response = client.post("/api/devices/import", json={"csv_data": csv_data, **options})
    assert response.status_code == 200, response.text
    return response.json()


def device_by_name(client, name):
    items = client.get("/api/devices", params={"q": name}).json()["items"]
    return next((d for d in items if d["name"] == name), None)


def test_import_ed_export(client):
    result = run_import(client, [
        "dev-imp-01;active;Sede Export;Sala 1;Rack 1;10;Cisco;C9300;Core;192.168.1.1/24;SN12345;AST-99;Test import",
        "dev-imp-02;planned;Sede Export;Sala 1;Rack 1;12;HPE;2930;Switch;192.168.1.2/24;SN67890;AST-100;Secondo",
    ])
    assert result["created_count"] == 2 and result["errors"] == []

    exp_csv = client.get("/api/devices/export", params={"format": "csv", "q": "dev-imp"})
    assert exp_csv.status_code == 200
    assert "dev-imp-01" in exp_csv.text and "192.168.1.1/24" in exp_csv.text and "Cisco" in exp_csv.text

    exp_json = client.get("/api/devices/export", params={"format": "json", "q": "dev-imp"}).json()
    assert [d["name"] for d in exp_json] == ["dev-imp-01", "dev-imp-02"]
    assert exp_json[0]["primary_ip"] == "192.168.1.1/24" and exp_json[0]["site"] == "Sede Export"


def test_template_scaricabile(client):
    template = client.get("/api/devices/import/template")
    assert template.status_code == 200 and "name" in template.text


def test_csv_vuoto_o_senza_colonna_nome(client):
    empty = client.post("/api/devices/import", json={"csv_data": "   "})
    assert empty.status_code == 200 and empty.json()["errors"]

    no_name = run_import(client, ["Sede;SN1"], header="site;serial")
    assert no_name["created_count"] == 0 and "name" in no_name["errors"][0]["error"]


def test_una_riga_sbagliata_non_blocca_le_altre(client):
    result = run_import(client, [
        "sw-1;active;Sede;;;;;;;;;AST-1;",
        "sw-2;active;Sede;;;;;;;;;AST-1;",              # asset tag duplicato
        f"{'x' * 150};active;Sede;;;;;;;;;;",             # nome troppo lungo
        "sw-3;stato-inventato;Sede;;;;;;;;;;",            # stato non valido
        "sw-4;pianificato;Sede;;;;;;;;;;",                # stato in italiano: accettato
        "sw-5;active;Sede;;;;;;;;;;",
    ])
    assert sorted(result["created_devices"]) == ["sw-1", "sw-4", "sw-5"]
    assert [e["row"] for e in result["errors"]] == [3, 4, 5]
    assert device_by_name(client, "sw-4")["status"] == "planned"
    assert device_by_name(client, "sw-2") is None


def test_simulazione_non_scrive_niente(client):
    result = run_import(client, ["sw-1;active;Sede nuova;;;;;;;;;;", "sw-2;boh;Sede nuova;;;;;;;;;;"], dry_run=True)
    assert result["dry_run"] is True and result["created_count"] == 1 and len(result["errors"]) == 1
    assert client.get("/api/devices").json()["total"] == 0
    assert client.get("/api/sites").json()["total"] == 0


def test_aggiornamento_tocca_solo_le_colonne_presenti(client):
    run_import(client, ["sw-1;planned;Sede;;;;;;;;SN-OLD;;nota"])
    result = run_import(client, ["sw-1;SN-NEW"], header="nome;seriale")
    assert result["updated_count"] == 1 and result["errors"] == []
    device = device_by_name(client, "sw-1")
    assert device["serial"] == "SN-NEW"
    assert device["status"] == "planned" and device["description"] == "nota"


def test_ip_gia_usato_da_un_altro_device(client):
    run_import(client, ["sw-1;active;Sede;;;;;;;10.0.0.1/24;;;"])
    result = run_import(client, ["sw-2;active;Sede;;;;;;;10.0.0.1/24;;;"])
    assert result["created_count"] == 0 and "sw-1" in result["errors"][0]["error"]
    ip = client.get("/api/ip-addresses").json()["items"][0]
    assert ip["device_name"] == "sw-1"


def test_export_reimportato_aggiorna_senza_errori(client):
    run_import(client, [
        "core;active;Sede;CED;R1;40;Cisco;C9300;Core;10.0.0.1/24;SN1;AST-1;core",
        "sw;planned;Sede;Piano 1;;;HPE;2930F;Accesso;10.0.0.2/24;SN2;;",
    ])
    exported = client.get("/api/devices/export", params={"format": "csv"}).text
    response = client.post("/api/devices/import", json={"csv_data": exported})
    result = response.json()
    assert result["errors"] == [] and result["created_count"] == 0 and result["updated_count"] == 2
    assert client.get("/api/sites").json()["total"] == 1
    assert client.get("/api/ip-addresses").json()["total"] == 2
