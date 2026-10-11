"""Token API e webhook delle modifiche."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import ApiToken, AuditEntry, Webhook
from app.services import webhooks
from app.services.webhooks import WebhookError, deliver
from tests.conftest import ADMIN
from tests.test_api import create


def bearer(token):
    other = TestClient(app)
    other.headers["Authorization"] = f"Bearer {token}"
    return other


# ---------------------------------------------------------------- token API
def test_token_api(client, session_factory):
    made = client.post("/api/api-tokens", json={"name": "GLPI", "expires_days": 30})
    assert made.status_code == 201, made.text
    token = made.json()["token"]
    assert token.startswith("nmt_") and made.json()["prefix"] == token[:10] and made.json()["username"] == "admin"
    assert "token" not in client.get("/api/api-tokens").json()[0]  # il testo intero solo alla creazione

    api = bearer(token)
    assert api.get("/api/devices").status_code == 200
    site = api.post("/api/sites", json={"name": "Da script"})
    assert site.status_code == 201
    entry = client.get("/api/audit-log?limit=1").json()["items"][0]
    assert (entry["username"], entry["source"]) == ("admin", "api")
    assert client.get("/api/api-tokens").json()[0]["last_used_at"]

    # Con un token non si gestiscono token e password
    assert api.get("/api/api-tokens").status_code == 403
    assert api.post("/api/api-tokens", json={"name": "altro"}).status_code == 403
    assert api.post("/api/auth/password", json={"current_password": ADMIN["password"], "new_password": "nuova-password-1"}).status_code == 403

    # Sola lettura
    ro = bearer(client.post("/api/api-tokens", json={"name": "Lettura", "read_only": True}).json()["token"])
    assert ro.get("/api/sites").status_code == 200
    assert ro.post("/api/sites", json={"name": "No"}).status_code == 403

    # Token sbagliato, revocato, scaduto
    assert bearer("nmt_inventato").get("/api/devices").status_code == 401
    token_id = made.json()["id"]
    with session_factory() as db:
        db.get(ApiToken, token_id).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    expired = api.get("/api/devices")
    assert expired.status_code == 401 and "scaduto" in expired.json()["detail"]
    assert client.delete(f"/api/api-tokens/{token_id}").status_code == 204
    assert api.get("/api/devices").status_code == 401


def test_token_di_altri_utenti(client, anonymous):
    viewer = create(client, "/users", {"username": "lettore", "password": "password-lettore", "role": "viewer"})
    # L'amministratore crea un token per un altro utente: vale con i permessi di quell'utente
    token = client.post("/api/api-tokens", json={"name": "Per lettore", "user_id": viewer["id"]}).json()["token"]
    api = bearer(token)
    assert api.get("/api/sites").status_code == 200
    assert api.post("/api/sites", json={"name": "No"}).status_code == 403

    # Il lettore vede e crea solo i suoi
    assert anonymous.post("/api/auth/login", json={"username": "lettore", "password": "password-lettore"}).status_code == 200
    mine = anonymous.post("/api/api-tokens", json={"name": "Mio"})
    assert mine.status_code == 201
    assert {t["name"] for t in anonymous.get("/api/api-tokens").json()} == {"Per lettore", "Mio"}
    assert anonymous.post("/api/api-tokens", json={"name": "Furbo", "user_id": 1}).status_code == 403
    assert len(client.get("/api/api-tokens").json()) == 2  # l'amministratore li vede tutti

    # Cambio password o utente disattivato: i token non valgono più
    client.patch(f"/api/users/{viewer['id']}", json={"password": "altra-password-1"})
    assert api.get("/api/sites").status_code == 401
    other = bearer(client.post("/api/api-tokens", json={"name": "Nuovo", "user_id": viewer["id"]}).json()["token"])
    assert other.get("/api/sites").status_code == 200
    client.patch(f"/api/users/{viewer['id']}", json={"active": False})
    assert other.get("/api/sites").status_code == 401


# ---------------------------------------------------------------- webhook
@pytest.fixture()
def sent(monkeypatch):
    """Richieste mandate ai webhook (al posto di urlopen)."""
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b""

    def urlopen(request, timeout=None, context=None):
        if calls and calls[-1] == "errore":
            calls.pop()
            raise webhooks.urllib.error.URLError("connessione rifiutata")
        calls.append({"url": request.full_url, "headers": dict(request.header_items()), "body": request.data})
        return Response()

    monkeypatch.setattr(webhooks.urllib.request, "urlopen", urlopen)
    return calls


def test_webhook(client, session_factory, sent):
    create(client, "/sites", {"name": "Prima del webhook"})  # lo storico di prima non si manda
    hook = client.post("/api/webhooks", json={
        "name": "CMDB", "url": "https://cmdb.example.com/hook?key=segreta", "secret": "chiave", "object_types": ["device"],
    })
    assert hook.status_code == 201, hook.text
    hook = hook.json()
    assert hook["url_host"] == "cmdb.example.com" and hook["has_secret"] and "url" not in hook
    assert client.post("/api/webhooks", json={"name": "X", "url": "ftp://x"}).status_code == 422
    assert client.post("/api/webhooks", json={"name": "Y", "url": "https://x", "object_types": ["boh"]}).status_code == 422

    site = create(client, "/sites", {"name": "Sede"})
    device = create(client, "/devices", {"name": "sw-01", "site_id": site["id"]})
    client.patch(f"/api/devices/{device['id']}", json={"name": "sw-02"})

    with session_factory() as db:
        row = db.get(Webhook, hook["id"])
        assert deliver(db, row) == 2
        assert deliver(db, row) == 0  # niente di nuovo
    [call] = sent
    assert call["url"] == "https://cmdb.example.com/hook?key=segreta"
    signature = "sha256=" + hmac.new(b"chiave", call["body"], hashlib.sha256).hexdigest()
    assert call["headers"]["X-netmap-signature"] == signature
    body = json.loads(call["body"])
    assert body["event"] == "changes"
    created, renamed = body["events"]
    assert (created["action"], created["object_type"], created["object"], created["api"]) == (
        "create", "device", "sw-01", f"/api/devices/{device['id']}")
    assert renamed["changes"] == [{"field": "Nome", "before": "sw-01", "after": "sw-02"}]
    assert renamed["user"] == "admin" and renamed["device_ids"] == [device["id"]]

    # Servizio giù: errore salvato, il cursore resta; al giro dopo arriva tutto
    client.delete(f"/api/devices/{device['id']}")
    sent.append("errore")
    with session_factory() as db:
        row = db.get(Webhook, hook["id"])
        cursor = row.cursor
        with pytest.raises(WebhookError):
            deliver(db, row)
        db.rollback()
        assert db.get(Webhook, hook["id"]).cursor == cursor
        assert deliver(db, db.get(Webhook, hook["id"])) == 1
    assert json.loads(sent[-1]["body"])["events"][0]["action"] == "delete"

    # Prova dalla pagina
    assert client.post(f"/api/webhooks/{hook['id']}/test").json() == {"ok": True}
    assert json.loads(sent[-1]["body"])["event"] == "test"


def test_webhook_righe_arrivate_dopo(client, session_factory, sent):
    """Righe con id più bassi che diventano visibili dopo (transazione lunga): arrivano lo stesso."""
    hook = client.post("/api/webhooks", json={"name": "Tutto", "url": "http://cmdb.local/hook"}).json()

    def add(db, entry_id, label):
        db.add(AuditEntry(id=entry_id, source="import", object_type="site", object_id=entry_id, label=label,
                          action="create", changes=[]))
        db.commit()

    with session_factory() as db:
        row = db.get(Webhook, hook["id"])
        base = row.cursor + 1  # la riga della creazione del webhook stesso
        deliver(db, row)
        add(db, base + 10, "dopo")
        assert deliver(db, row) == 1
        assert row.gaps and row.gaps[0][:2] == [base + 1, base + 9]
        add(db, base + 3, "in ritardo")
        add(db, base + 5, "in ritardo 2")
        assert deliver(db, row) == 2
        assert [g[:2] for g in row.gaps] == [[base + 1, base + 2], [base + 4, base + 4], [base + 6, base + 9]]
    labels = [e["object"] for call in sent for e in json.loads(call["body"])["events"]]
    assert labels[-3:] == ["dopo", "in ritardo", "in ritardo 2"]
