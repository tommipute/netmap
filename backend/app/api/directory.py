"""Impostazioni dell'accesso con Active Directory (solo admin) e prova con un utente vero prima di salvarle."""
import ssl

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.database import get_db
from app.models import DirectorySettings, User
from app.models.enums import UserRole, UserSource
from app.schemas.auth import DirectorySettingsRead, DirectorySettingsWrite, DirectoryTest
from app.services import directory

router = APIRouter(tags=["Active Directory"], dependencies=[Depends(require_admin)])


def _read(db: Session, row: DirectorySettings) -> DirectorySettingsRead:
    data = DirectorySettingsRead.model_validate(row)
    data.local_admins = db.scalar(select(func.count(User.id)).where(
        User.role == UserRole.ADMIN.value, User.active.is_(True), User.source == UserSource.LOCAL.value)) or 0
    data.domain_users = db.scalar(select(func.count(User.id)).where(User.source == UserSource.AD.value)) or 0
    return data


def _check(payload: DirectorySettingsWrite) -> None:
    if payload.ca_cert:
        try:
            ssl.create_default_context(cadata=payload.ca_cert)
        except (ssl.SSLError, ValueError, TypeError):
            raise HTTPException(422, "Il certificato della CA non è valido: serve il testo PEM (-----BEGIN CERTIFICATE-----...)")
    if not payload.enabled:
        return
    if not directory.server_list(payload.servers):
        raise HTTPException(422, "Indica almeno un domain controller")
    if not payload.domain.strip():
        raise HTTPException(422, "Indica il dominio (per esempio azienda.local)")
    if not (payload.admin_group or payload.editor_group or payload.viewer_group or payload.default_role):
        raise HTTPException(422, "Indica almeno un gruppo, o un ruolo per chi non è in nessun gruppo")


def _apply(row: DirectorySettings, payload: DirectorySettingsWrite) -> DirectorySettings:
    for key, value in payload.model_dump().items():
        setattr(row, key, value.strip() if isinstance(value, str) else value)
    return row


@router.get("/directory", response_model=DirectorySettingsRead, summary="Impostazioni di Active Directory")
def get_settings(db: Session = Depends(get_db)):
    row = directory.settings_row(db)
    db.commit()
    return _read(db, row)


@router.put("/directory", response_model=DirectorySettingsRead, summary="Salva le impostazioni di Active Directory")
def save_settings(payload: DirectorySettingsWrite, db: Session = Depends(get_db)):
    _check(payload)
    row = _apply(directory.settings_row(db), payload)
    db.commit()
    return _read(db, row)


@router.post("/directory/test", summary="Prova le impostazioni (anche non salvate) con un utente del dominio")
def test_settings(payload: DirectoryTest):
    _check(payload.settings.model_copy(update={"enabled": True}))
    cfg = _apply(DirectorySettings(), payload.settings)  # mai aggiunto alla sessione: non si salva
    try:
        found = directory.authenticate(cfg, payload.username, payload.password, check_all=True)
    except directory.DirectoryError as exc:
        return {"ok": False, "message": str(exc)}
    except directory.LoginDenied as exc:
        return {"ok": False, "message": str(exc)}
    if found is None:
        return {"ok": False, "message": "Nome utente o password sbagliati"}
    return {
        "ok": True,
        "message": None,
        "user": {"username": found.username, "dn": found.dn, "first_name": found.first_name, "last_name": found.last_name, "email": found.email},
        "role": found.role,
        "by_default": found.role is not None and not any(g.member for g in found.groups),
        "groups": [{"role": g.role, "group": g.group, "found": g.dn is not None, "member": g.member} for g in found.groups],
    }
