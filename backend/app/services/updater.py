"""Scambio di file con l'updater che gira sull'host (updater/updater.sh).

L'app non si aggiorna da sola: legge status.json e updater.log, scrive request.json (controlla, aggiorna, backup,
ripristina un backup, raccogli i log dei container per il pacchetto diagnostico) e settings.json. Nessun accesso a Docker né a GitHub da qui.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

DEFAULT_SETTINGS = {
    "auto_update": False,
    "branch": "main",
    "channel": "stable",
    "check_interval_minutes": 60,
    "keep_backups": 10,
    # Backup notturno del database fatto dallo script (oltre a quello prima di ogni aggiornamento)
    "backup_daily": True,
    "backup_time": "02:30",
    "backup_keep_days": 14,
}
# Una richiesta più importante non viene sostituita da una meno importante ancora in attesa
PRIORITY = {"check": 0, "diagnostics": 1, "backup": 2, "update": 3, "restore": 4}
# Il timer gira ogni minuto: oltre questo silenzio lo script è considerato fermo
SILENT_AFTER_MINUTES = 5
# Un aggiornamento (build compresa) che dura più di così è bloccato
BUSY_TOO_LONG_MINUTES = 120
LOG_MAX_BYTES = 200_000


def folder() -> Path:
    return Path(settings.updater_dir)


def mounted() -> bool:
    path = folder()
    return path.is_dir() and os.access(path, os.W_OK)


def read_json(name: str) -> dict | None:
    try:
        data = json.loads((folder() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_json(name: str, data: dict) -> None:
    """Scrittura atomica (file temporaneo e rename): lo script non legge mai un file a metà."""
    path = folder() / name
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
        os.chmod(tmp, 0o664)  # lo script gira con un altro utente e la deve poter rimpiazzare
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def current_settings() -> dict:
    stored = read_json("settings.json") or {}
    return {key: stored.get(key, value) for key, value in DEFAULT_SETTINGS.items()}


def pending_request() -> dict | None:
    request = read_json("request.json")
    return request if request and request.get("action") else None


def request(action: str, username: str | None, **extra) -> dict:
    """extra: dati della richiesta (restore: file = nome del backup)."""
    current = pending_request()
    if current and PRIORITY.get(current["action"], 0) > PRIORITY[action]:
        return current  # es. "aggiorna" comprende già il controllo
    data = {"action": action, "requested_at": datetime.now(timezone.utc).isoformat(), "requested_by": username or "", **extra}
    write_json("request.json", data)
    return data


def _minutes_since(value: str | None) -> float | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds() / 60


def overview() -> dict:
    status = read_json("status.json")
    silent = _minutes_since(status.get("last_run")) if status else None
    busy = status.get("activity") not in (None, "idle") if status else False
    busy_for = _minutes_since(status.get("activity_since")) if busy else None
    if not mounted():
        script = "not_mounted"
    elif status is None:
        script = "never_ran"
    elif busy:
        script = "stuck" if busy_for is not None and busy_for > BUSY_TOO_LONG_MINUTES else "ok"
    else:
        script = "silent" if silent is None or silent > SILENT_AFTER_MINUTES else "ok"
    return {
        "mounted": mounted(),
        "script": script,
        "silent_minutes": round(silent) if silent is not None else None,
        "status": status,
        "request": pending_request(),
        "settings": current_settings(),
    }


def read_log() -> str:
    path = folder() / "updater.log"
    try:
        with path.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - LOG_MAX_BYTES))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
