"""Campi personalizzati definiti dall'amministratore: valori controllati, filtri, ordinamento, ricerca, export."""
from tests.test_discovery import create


def _setup(client):
    site = create(client, "/sites", {"name": "Sede"})
    create(client, "/custom-fields", {"name": "contratto", "label": "Contratto", "type": "select",
                                      "choices": ["Base", " Oro ", "Oro", ""], "object_types": ["devices"],
                                      "required": True})
    create(client, "/custom-fields", {"name": "anni", "label": "Anni", "type": "number", "object_types": ["devices"]})
    create(client, "/custom-fields", {"name": "ups", "label": "Sotto UPS", "type": "bool", "object_types": ["devices"]})
    create(client, "/custom-fields", {"name": "scadenza", "label": "Scadenza", "type": "date", "object_types": ["devices", "sites"]})
    return site


def test_definizioni_e_valori_controllati(client):
    site = _setup(client)
    fields = client.get("/api/custom-fields").json()["items"]
    assert [f["choices"] for f in fields if f["name"] == "contratto"] == [["Base", "Oro"]]
    # Nome non valido, oggetto sconosciuto, scelta senza valori
    assert client.post("/api/custom-fields", json={"name": "Con Spazi", "label": "x", "object_types": ["devices"]}).status_code == 422
    assert client.post("/api/custom-fields", json={"name": "x", "label": "x", "object_types": ["mappe"]}).status_code == 422
    assert client.post("/api/custom-fields", json={"name": "y", "label": "y", "type": "select", "object_types": ["devices"]}).status_code == 422
    assert client.post("/api/custom-fields", json={"name": "anni", "label": "Doppio", "object_types": ["devices"]}).status_code == 409

    base = {"name": "sw1", "site_id": site["id"]}
    r = client.post("/api/devices", json=base)
    assert r.status_code == 422 and "Contratto" in r.json()["detail"]
    r = client.post("/api/devices", json={**base, "custom_fields": {"contratto": "Platino"}})
    assert r.status_code == 422 and "Base, Oro" in r.json()["detail"]
    r = client.post("/api/devices", json={**base, "custom_fields": {"contratto": "Oro", "anni": "tre"}})
    assert r.status_code == 422 and "numero" in r.json()["detail"]
    r = client.post("/api/devices", json={**base, "custom_fields": {"contratto": "Oro", "scadenza": "31/12/2027"}})
    assert r.status_code == 422 and "data" in r.json()["detail"]
    device = create(client, "/devices", {**base, "custom_fields": {
        "contratto": "Oro", "anni": "3,0", "ups": "sì", "scadenza": "2027-12-31", "scadenza_vecchia": "libero", "note": ""}})
    # Numeri e sì/no convertiti; le chiavi senza definizione restano com'erano; i vuoti definiti spariscono
    assert device["custom_fields"] == {"contratto": "Oro", "anni": 3, "ups": True, "scadenza": "2027-12-31",
                                       "scadenza_vecchia": "libero", "note": ""}
    r = client.patch(f"/api/devices/{device['id']}", json={"custom_fields": {"contratto": "Base", "anni": ""}})
    assert r.status_code == 200 and r.json()["custom_fields"] == {"contratto": "Base"}
    # Le altre modifiche non toccano i campi personalizzati
    assert client.patch(f"/api/devices/{device['id']}", json={"description": "x"}).status_code == 200
    # Il campo vale solo per gli oggetti scelti: la sede ha la data ma non il contratto obbligatorio
    assert create(client, "/sites", {"name": "Altra", "custom_fields": {"scadenza": "2026-01-02"}})["custom_fields"] == {"scadenza": "2026-01-02"}

    # Il nome non si cambia (i valori resterebbero senza campo), l'etichetta sì
    anni = next(f for f in fields if f["name"] == "anni")
    assert client.patch(f"/api/custom-fields/{anni['id']}", json={"name": "eta"}).status_code == 422
    assert client.patch(f"/api/custom-fields/{anni['id']}", json={"name": "anni", "label": "Età"}).status_code == 200


def test_filtri_ordinamento_ricerca_ed_export(client):
    site = _setup(client)
    for name, contract, years, ups in (("a", "Oro", 10, True), ("b", "Base", 9, False), ("c", "Oro", None, None)):
        values = {"contratto": contract, "anni": years, "ups": ups}
        create(client, "/devices", {"name": name, "site_id": site["id"], "custom_fields": values})

    def names(**params):
        return [d["name"] for d in client.get("/api/devices", params=params).json()["items"]]

    assert names(cf_contratto__eq="Oro") == ["a", "c"]
    assert names(cf_contratto__contains="as") == ["b"]
    assert names(cf_ups__eq="true") == ["a"]
    assert names(cf_anni__isnull="true") == ["c"]
    assert names(sort="cf_anni") == ["b", "a", "c"]  # come numeri: 9 prima di 10, i vuoti in fondo
    assert names(sort="-cf_anni") == ["a", "b", "c"]
    assert names(q="base") == ["b"]
    assert client.get("/api/devices", params={"cf_sconosciuto__eq": "x"}).status_code == 422
    assert [r["label"] for r in client.get("/api/search", params={"q": "base"}).json()] == ["b"]

    csv = client.get("/api/devices/export", params={"cf_contratto__eq": "Oro"}).text
    header, *rows = csv.lstrip("﻿").strip().splitlines()
    assert header.endswith(";description;cf_anni;cf_contratto;cf_scadenza;cf_ups")  # nell'ordine dei moduli
    assert rows[0].startswith("a;") and rows[0].endswith(";10;Oro;;sì") and len(rows) == 2
    exported = client.get("/api/devices/export", params={"format": "json", "name__eq": "b"}).json()
    assert exported[0]["custom_fields"] == {"contratto": "Base", "anni": 9, "ups": False}


def test_solo_l_amministratore_cambia_i_campi(client, anonymous):
    create(client, "/users", {"username": "tecnico", "password": "tecnico-123", "role": "editor"})
    anonymous.post("/api/auth/login", json={"username": "tecnico", "password": "tecnico-123"})
    assert anonymous.get("/api/custom-fields").status_code == 200
    r = anonymous.post("/api/custom-fields", json={"name": "x", "label": "x", "object_types": ["devices"]})
    assert r.status_code == 403
