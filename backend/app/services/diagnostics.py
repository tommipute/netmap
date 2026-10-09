"""Pacchetto diagnostico: uno zip con versione, configurazione (senza segreti), stato del database e log.

Serve a capire un problema senza entrare sul server: l'amministratore lo scarica dalla pagina Aggiornamenti e lo
allega a una segnalazione. Niente password, chiavi né dati della rete (device, IP, nomi utente) nel riepilogo;
i log invece possono contenerne, e il LEGGIMI lo dice. Ogni parte è raccolta da sola: se una non riesce,
l'errore finisce nel riepilogo e il resto c'è lo stesso.
"""
import io
import json
import platform
import re
import sys
import zipfile
from datetime import datetime, timezone
from importlib import metadata

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.core import logbuffer
from app.models import (
    AlertChannel, BackupCopy, BackupTarget, BackupTask, Base, Device, DirectorySettings, DiscoveryChange, DiscoveryJob,
    DiscoveryRun, User,
)
from app.models.enums import ChangeStatus, DeviceStatus, RunStatus
from app.services import directory, keys, updater

PACKAGES = ("fastapi", "uvicorn", "sqlalchemy", "alembic", "pydantic", "psycopg", "pysnmp", "ldap3", "cryptography", "paramiko", "smbprotocol")
SECRET_SETTINGS = ("secrets_key", "auth_secret")
UPDATER_FILES = ("status.json", "settings.json", "request.json", "updater.log")
HOST_REPORT = "diagnostics/host.txt"
RUN_LOG_LINES = 30
README = """Pacchetto diagnostico di NetMap
================================

Creato il {at} da NetMap {version}.

netmap.json         versione, migration, configurazione (password e chiavi tolte), database (righe per tabella),
                    utenti per ruolo (senza nomi), Active Directory, avvisi, copie dei backup, ultime scansioni
api.log             ultime righe di log dell'API (dall'ultimo avvio)
updater/            stato, impostazioni e log dello script di aggiornamento sul server
updater/host.txt    disco, memoria, container e loro log: c'è solo se è stato chiesto
                    «Raccogli i log dei container» nella pagina Aggiornamenti

ATTENZIONE: i log possono contenere indirizzi IP, nomi dei device e nomi utente della tua rete.
Password, chiavi e token sono tolti dal riepilogo e dai file di configurazione, ma prima di mandare
il pacchetto a qualcuno dagli un'occhiata.

-----

NetMap diagnostic package. netmap.json: version, configuration without secrets, database statistics.
api.log and updater/: logs. WARNING: logs may contain IP addresses, device names and user names of your network.
"""


def _mask_url(value: str) -> str:
    return re.sub(r"(://[^:/@]+):[^@]*@", r"\1:***@", value)


def masked_settings() -> dict:
    data = settings.model_dump()
    for key in SECRET_SETTINGS:
        data[key] = "***" if data.get(key) else ""
    data["database_url"] = _mask_url(data.get("database_url") or "")
    return data


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _versions() -> dict:
    found = {}
    for name in PACKAGES:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return found


def _migrations(db: Session) -> dict:
    from app.api.system import migration_heads, migration_state

    try:
        with db.begin_nested():
            applied = sorted(row[0] for row in db.execute(text("SELECT version_num FROM alembic_version")))
    except Exception:  # noqa: BLE001 - niente alembic (database dei test)
        applied = []
    return {"state": migration_state(db), "database": applied, "code": sorted(migration_heads())}


def _database(db: Session) -> dict:
    dialect = db.get_bind().dialect.name
    info: dict = {"dialect": dialect}
    if dialect == "postgresql":
        info["server"] = db.scalar(text("SELECT version()"))
        info["size_bytes"] = db.scalar(text("SELECT pg_database_size(current_database())"))
        info["connections"] = db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"))
    tables = sorted(Base.metadata.sorted_tables, key=lambda table: table.name)
    info["rows"] = {table.name: db.scalar(select(func.count()).select_from(table)) for table in tables}
    return info


def _users(db: Session) -> dict:
    rows = db.execute(select(User.role, User.source, User.active, func.count()).group_by(User.role, User.source, User.active))
    return {
        "auth_enabled": settings.auth_enabled,
        "users": [{"role": role, "source": source, "active": active, "count": count} for role, source, active, count in rows],
    }


def _directory(db: Session) -> dict:
    cfg = db.scalars(select(DirectorySettings).order_by(DirectorySettings.id)).first()
    if cfg is None:
        return {"enabled": False}
    return {
        "enabled": cfg.enabled,
        "security": cfg.security,
        "port": cfg.port,
        "verify_cert": cfg.verify_cert,
        "ca_cert": bool(cfg.ca_cert),
        "servers": len(directory.server_list(cfg.servers)),
        "base_dn": bool(cfg.base_dn),
        "groups": {role: bool(getattr(cfg, column)) for role, column in directory.ROLE_GROUPS},
        "default_role": cfg.default_role,
    }


def _alerts(db: Session) -> list:
    return [
        {"type": c.type, "enabled": c.enabled, "language": c.language, "delay_minutes": c.delay_minutes,
         "has_secret": c.has_secret, "last_sent_at": _iso(c.last_sent_at), "last_error": c.last_error}
        for c in db.scalars(select(AlertChannel).order_by(AlertChannel.id))
    ]


def _backups(db: Session) -> dict:
    copies = dict(db.execute(select(BackupCopy.target_id, func.count()).group_by(BackupCopy.target_id)).all())
    targets = [
        {"type": b.type, "enabled": b.enabled, "keep_days": b.keep_days, "include_key": b.include_key,
         "copies": copies.get(b.id, 0), "last_copy_at": _iso(b.last_copy_at), "last_error": b.last_error,
         "last_error_at": _iso(b.last_error_at)}
        for b in db.scalars(select(BackupTarget).order_by(BackupTarget.id))
    ]
    tasks = [
        {"action": task.action, "status": task.status, "message": task.message, "created_at": _iso(task.created_at),
         "finished_at": _iso(task.finished_at)}
        for task in db.scalars(select(BackupTask).order_by(BackupTask.id.desc()).limit(10))
    ]
    return {"targets": targets, "recent_tasks": tasks, "secrets": keys.status(db)}


def _devices(db: Session) -> dict:
    rows = db.execute(select(Device.reachable, func.count()).where(Device.status == DeviceStatus.ACTIVE.value).group_by(Device.reachable))
    by_state = {("unknown" if reachable is None else "up" if reachable else "down"): count for reachable, count in rows}
    return {
        "monitor_interval_seconds": settings.monitor_interval_seconds,
        "active_devices": by_state,
        "last_check_at": _iso(db.scalar(select(func.max(Device.last_check_at)))),
    }


def _discovery(db: Session) -> dict:
    runs = []
    for run in db.scalars(select(DiscoveryRun).order_by(DiscoveryRun.id.desc()).limit(20)):
        item = {
            "id": run.id, "job_id": run.job_id, "status": run.status, "requested_at": _iso(run.requested_at),
            "started_at": _iso(run.started_at), "finished_at": _iso(run.finished_at), "hosts_total": run.hosts_total,
            "hosts_responded": run.hosts_responded, "changes_proposed": run.changes_proposed,
            "changes_applied": run.changes_applied,
        }
        if run.status == RunStatus.FAILED.value:  # il log di una scansione fallita è quello che serve per capire perché
            item["log_tail"] = (run.log or "").splitlines()[-RUN_LOG_LINES:]
        runs.append(item)
    pending = db.scalar(select(func.count()).select_from(DiscoveryChange).where(DiscoveryChange.status == ChangeStatus.PENDING.value))
    jobs = db.scalar(select(func.count()).select_from(DiscoveryJob))
    return {"jobs": jobs, "pending_changes": pending, "recent_runs": runs}


SECTIONS = {
    "migrations": _migrations,
    "database": _database,
    "auth": _users,
    "directory": _directory,
    "alerts": _alerts,
    "backups": _backups,
    "monitor": _devices,
    "discovery": _discovery,
}


def summary(db: Session) -> dict:
    from app.api.system import version_info

    data: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": version_info(),
        "runtime": {"python": sys.version.split()[0], "platform": platform.platform(), "packages": _versions()},
        "settings": masked_settings(),
    }
    errors = []
    for name, collect in SECTIONS.items():
        try:
            with db.begin_nested():
                data[name] = collect(db)
        except Exception as exc:  # noqa: BLE001 - una parte rotta non deve togliere le altre
            data[name] = None
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    overview = updater.overview()
    data["updater"] = {"mounted": overview["mounted"], "script": overview["script"],
                       "silent_minutes": overview["silent_minutes"], "request": overview["request"]}
    report = updater.folder() / HOST_REPORT
    try:
        stat = report.stat()
        data["host_report"] = {"collected_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(), "size": stat.st_size}
    except OSError:
        data["host_report"] = None
    data["errors"] = errors
    return data


def build(db: Session) -> tuple[str, bytes]:
    """Nome del file e contenuto dello zip."""
    data = summary(db)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("LEGGIMI.txt", README.format(at=data["generated_at"], version=data["version"]["version"] or data["version"]["short"] or "?"))
        zf.writestr("netmap.json", json.dumps(data, indent=2, ensure_ascii=False, default=str))
        zf.writestr("api.log", logbuffer.buffer.text() + "\n")
        folder = updater.folder()
        for name in (*UPDATER_FILES, HOST_REPORT):
            path = folder / name
            if path.is_file():
                try:
                    zf.write(path, f"updater/{path.name}")
                except OSError:
                    continue
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"netmap-diagnostica-{stamp}.zip", buffer.getvalue()
