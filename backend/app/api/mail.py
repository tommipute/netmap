"""Server di posta dei canali email (solo admin) e prova con le impostazioni anche non salvate."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.secrets import SecretError, encrypt
from app.database import get_db
from app.models import AlertChannel, MailSettings
from app.schemas.alerts import MailSettingsRead, MailSettingsWrite, MailTest
from app.services import mail

router = APIRouter(tags=["Avvisi"], dependencies=[Depends(require_admin)])


def _read(db: Session, row: MailSettings) -> MailSettingsRead:
    data = MailSettingsRead.model_validate(row)
    email = select(func.count(AlertChannel.id)).where(AlertChannel.type == "email")
    data.channels = db.scalar(email.where(AlertChannel.smtp_custom.is_(False))) or 0
    data.custom_channels = db.scalar(email.where(AlertChannel.smtp_custom.is_(True))) or 0
    return data


def _apply(row: MailSettings, payload: MailSettingsWrite) -> MailSettings:
    for key in ("host", "username", "sender"):
        setattr(row, key, (getattr(payload, key) or "").strip() or None)
    row.port, row.security = payload.port, payload.security
    if payload.password is not None:
        try:
            row.password_enc = encrypt(payload.password) if payload.password else None
        except SecretError as exc:
            raise HTTPException(500, str(exc)) from exc
    return row


@router.get("/mail-settings", response_model=MailSettingsRead, summary="Server di posta")
def get_settings(db: Session = Depends(get_db)):
    row = mail.settings_row(db)
    db.commit()
    return _read(db, row)


@router.put("/mail-settings", response_model=MailSettingsRead, summary="Salva il server di posta")
def save_settings(payload: MailSettingsWrite, db: Session = Depends(get_db)):
    row = mail.settings_row(db)
    if not (payload.host or "").strip() and _read(db, row).channels:
        raise HTTPException(422, "Ci sono canali di avviso che usano questo server: indica il server SMTP")
    _apply(row, payload)
    db.commit()
    return _read(db, row)


@router.post("/mail-settings/test", summary="Manda un'email di prova (con le impostazioni anche non salvate)")
def test_settings(payload: MailTest, db: Session = Depends(get_db)):
    if "@" not in payload.to:
        raise HTTPException(422, "Un destinatario non sembra un indirizzo email")
    saved = mail.settings_row(db)
    cfg = _apply(MailSettings(password_enc=saved.password_enc), payload.settings)  # mai aggiunto alla sessione
    db.rollback()
    try:
        mail.send_mail(mail.config_of(cfg), [payload.to.strip()], "NetMap: email di prova",
                       "Se leggi questo messaggio, NetMap riesce a mandare email con queste impostazioni.")
    except mail.MailError as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": None}
