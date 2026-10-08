import json
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings


@pytest.fixture()
def updater_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "updater_dir", str(tmp_path))
    return tmp_path


def test_health_e_versione(client, monkeypatch):
    monkeypatch.setattr(settings, "app_commit", "0123456789abcdef")
    monkeypatch.setattr(settings, "app_version", "2026.10.08-2")
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok" and health.json()["checks"]["database"] == "ok"
    assert health.json()["commit"] == "0123456789abcdef"
    version = client.get("/api/version").json()
    assert version["short"] == "0123456" and version["version"] == "2026.10.08-2"


def test_aggiornamenti_cartella_non_montata(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "updater_dir", str(tmp_path / "manca"))
    data = client.get("/api/updates").json()
    assert data["mounted"] is False and data["script"] == "not_mounted"
    assert client.post("/api/updates/request", json={"action": "check"}).status_code == 409


def test_aggiornamenti_richieste_e_impostazioni(client, updater_dir):
    data = client.get("/api/updates").json()
    assert data["mounted"] is True and data["script"] == "never_ran"
    assert data["settings"] == {
        "auto_update": False, "branch": "main", "channel": "stable", "check_interval_minutes": 60, "keep_backups": 10,
        "backup_daily": True, "backup_time": "02:30", "backup_keep_days": 14,
    }

    assert client.post("/api/updates/request", json={"action": "update"}).status_code == 202
    # "controlla" non sostituisce un "aggiorna" già in attesa
    client.post("/api/updates/request", json={"action": "check"})
    request = json.loads((updater_dir / "request.json").read_text())
    assert request["action"] == "update" and request["requested_by"] == "admin"
    assert client.post("/api/updates/request", json={"action": "reboot"}).status_code == 422
    (updater_dir / "request.json").write_text("{}")  # lo script l'ha presa
    client.post("/api/updates/request", json={"action": "backup"})
    client.post("/api/updates/request", json={"action": "check"})
    assert json.loads((updater_dir / "request.json").read_text())["action"] == "backup"

    new = {
        "auto_update": True, "branch": "release/1.x", "channel": "beta", "check_interval_minutes": 30, "keep_backups": 5,
        "backup_daily": False, "backup_time": "23:15", "backup_keep_days": 30,
    }
    assert client.put("/api/updates/settings", json=new).json() == new
    assert json.loads((updater_dir / "settings.json").read_text()) == new
    for branch in ("-x", "a..b", "a b", "rami/"):
        assert client.put("/api/updates/settings", json={**new, "branch": branch}).status_code == 422, branch
    assert client.put("/api/updates/settings", json={**new, "keep_backups": 0}).status_code == 422
    assert client.put("/api/updates/settings", json={**new, "channel": "nightly"}).status_code == 422
    for time in ("24:00", "2:30", "02:30; rm"):
        assert client.put("/api/updates/settings", json={**new, "backup_time": time}).status_code == 422, time


def test_aggiornamenti_stato_dello_script(client, updater_dir):
    now = datetime.now(timezone.utc)
    status = {"last_run": now.isoformat(), "activity": "idle", "history": [{"outcome": "success"}]}
    (updater_dir / "status.json").write_text(json.dumps(status))
    (updater_dir / "updater.log").write_text("riga 1\nriga 2\n")
    data = client.get("/api/updates").json()
    assert data["script"] == "ok" and data["status"]["history"][0]["outcome"] == "success"
    assert client.get("/api/updates/log").json()["text"].endswith("riga 2\n")

    status["last_run"] = (now - timedelta(minutes=30)).isoformat()
    (updater_dir / "status.json").write_text(json.dumps(status))
    assert client.get("/api/updates").json()["script"] == "silent"
    # Durante un aggiornamento lungo lo script non scrive last_run, ma non è fermo
    status.update(activity="updating", activity_since=(now - timedelta(minutes=10)).isoformat())
    (updater_dir / "status.json").write_text(json.dumps(status))
    assert client.get("/api/updates").json()["script"] == "ok"


def test_aggiornamenti_solo_admin(client, updater_dir):
    client.post("/api/users", json={"username": "lettore", "password": "password-lettore", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "lettore", "password": "password-lettore"})
    assert client.get("/api/updates").status_code == 403
    assert client.get("/api/health").status_code == 200  # health e versione restano pubblici
