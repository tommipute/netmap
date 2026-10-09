"""Avvisi: messaggio di prova di un canale (la configurazione è un CRUD in routes.py)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.database import get_db
from app.models import AlertChannel
from app.schemas.alerts import AlertPreviewRequest
from app.services.alerts import preview, send_test

router = APIRouter(tags=["Avvisi"], dependencies=[Depends(require_admin)])


@router.post("/alert-channels/{channel_id}/test", summary="Manda un messaggio di prova")
def test_channel(channel_id: int, db: Session = Depends(get_db)):
    channel = db.get(AlertChannel, channel_id)
    if channel is None:
        raise HTTPException(404, "Canale non trovato")
    error = send_test(db, channel)
    if error:
        raise HTTPException(502, f"Messaggio non inviato: {error}")
    return {"ok": True}


@router.post("/alert-messages/preview", summary="Come arriverebbero i messaggi con questi modelli (dati di esempio)")
def preview_messages(payload: AlertPreviewRequest):
    return preview(payload.language, payload.templates, payload.ports != "none")
