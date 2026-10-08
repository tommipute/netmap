"""Sistema: versione installata, controllo di salute (usato dall'updater) e pagina Aggiornamenti (solo admin)."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.config import settings
from app.database import get_db
from app.models import User
from app.services import updater

public = APIRouter(tags=["Sistema"])
BRANCH = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._/-]{0,99}")
admin = APIRouter(prefix="/updates", tags=["Aggiornamenti"], dependencies=[Depends(require_admin)])


def version_info() -> dict:
    return {
        "version": settings.app_version,
        "commit": settings.app_commit,
        "short": settings.app_commit[:7],
        "date": settings.app_commit_date,
        "tag": settings.app_tag,
    }


@lru_cache
def migration_heads() -> frozenset[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    base = Path(__file__).resolve().parents[2]  # cartella backend/
    config = Config(str(base / "alembic.ini"))
    config.set_main_option("script_location", str(base / "alembic"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())


def migration_state(db: Session) -> str:
    """ok = database all'ultima migration; pending = migration mancanti; unknown = niente alembic (es. test)."""
    try:
        with db.begin_nested():
            applied = {row[0] for row in db.execute(text("SELECT version_num FROM alembic_version"))}
    except Exception:
        return "unknown"
    return "ok" if applied == migration_heads() else "pending"


@public.get("/version")
def version():
    return version_info()


@public.get("/health")
def health(response: Response, db: Session = Depends(get_db)):
    checks = {"database": "ok", "migrations": "unknown"}
    try:
        db.execute(text("SELECT 1"))
        checks["migrations"] = migration_state(db)
    except Exception:
        checks["database"] = "error"
    ok = checks["database"] == "ok" and checks["migrations"] != "pending"
    if not ok:
        response.status_code = 503
    return {"status": "ok" if ok else "error", "checks": checks, **version_info()}


# ---------------------------------------------------------------------------------------- aggiornamenti
class UpdateSettings(BaseModel):
    auto_update: bool = False
    branch: str = "main"
    check_interval_minutes: int = Field(60, ge=5, le=10080)
    keep_backups: int = Field(10, ge=1, le=100)


class UpdateRequest(BaseModel):
    action: Literal["check", "update"]


def _require_folder() -> None:
    if not updater.mounted():
        raise HTTPException(409, "La cartella dell'updater non è montata nel container api: vedi README, Aggiornamenti automatici")


@admin.get("")
def updates_overview():
    return {**updater.overview(), "running": version_info()}


@admin.get("/log")
def updates_log():
    return {"text": updater.read_log()}


@admin.post("/request", status_code=202)
def updates_request(body: UpdateRequest, user: User | None = Depends(require_admin)):
    _require_folder()
    return updater.request(body.action, user.username if user else None)


@admin.put("/settings")
def updates_settings(body: UpdateSettings):
    _require_folder()
    # Il branch finisce in un comando git sull'host: solo nomi semplici
    if not BRANCH.fullmatch(body.branch) or ".." in body.branch or body.branch.endswith(("/", ".", ".lock")):
        raise HTTPException(422, "Nome del branch non valido")
    updater.write_json("settings.json", body.model_dump())
    return updater.current_settings()
