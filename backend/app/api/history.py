"""Storico delle modifiche (sola lettura): lo scrive services/audit.py a ogni salvataggio."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditEntry
from app.schemas.common import Page

router = APIRouter(tags=["Storico"])


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    at: datetime
    username: str | None
    source: str
    object_type: str
    object_id: int
    label: str
    action: str
    changes: list
    device_id: int | None
    device_id_2: int | None


@router.get("/audit-log", response_model=Page[AuditRead], summary="Storico delle modifiche, dalle più recenti")
def audit_log(
    device_id: int | None = Query(None, description="Modifiche che riguardano questo device (anche porte, IP, cavi)"),
    object_type: str | None = None,
    object_id: int | None = None,
    source: str | None = Query(None, description="utente / scansione / import / sistema"),
    q: str | None = Query(None, description="Cerca nel nome dell'oggetto e nell'utente"),
    since: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(AuditEntry)
    if device_id is not None:
        stmt = stmt.where(or_(AuditEntry.device_id == device_id, AuditEntry.device_id_2 == device_id))
    if object_type:
        stmt = stmt.where(AuditEntry.object_type == object_type)
    if object_id is not None:
        stmt = stmt.where(AuditEntry.object_id == object_id)
    if source:
        stmt = stmt.where(AuditEntry.source == source)
    if q:
        stmt = stmt.where(or_(AuditEntry.label.ilike(f"%{q}%"), AuditEntry.username.ilike(f"%{q}%")))
    if since is not None:
        stmt = stmt.where(AuditEntry.at >= since)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditEntry.at.desc(), AuditEntry.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": rows}
