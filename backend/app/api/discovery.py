"""Scansione SNMP: avvio dei job, storico delle esecuzioni, modifiche da approvare.
Profili e job hanno anche gli endpoint CRUD standard (registrati in routes.py)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.discovery import runner
from app.models import DiscoveryChange, DiscoveryJob, DiscoveryRun
from app.models.enums import ChangeStatus
from app.schemas.common import Page
from app.schemas.discovery import (
    ApproveResult,
    ChangeIds,
    DiscoveryChangeRead,
    DiscoveryRunRead,
    PendingCount,
    RejectResult,
)

router = APIRouter(tags=["Scansione"])


@router.post("/discovery-jobs/{job_id}/run", response_model=DiscoveryRunRead, status_code=202,
             summary="Mette in coda una scansione: il worker la avvia entro pochi secondi")
def run_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(DiscoveryJob, job_id)
    if job is None:
        raise HTTPException(404, "Elemento non trovato")
    if runner.active_run(db, job.id):
        raise HTTPException(409, "C'è già una scansione in coda o in corso per questo job")
    return runner.enqueue(db, job)


@router.get("/discovery-runs", response_model=Page[DiscoveryRunRead], summary="Storico delle scansioni")
def list_runs(job_id: int | None = None, limit: int = Query(20, ge=1, le=200), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db)):
    stmt = select(DiscoveryRun)
    if job_id is not None:
        stmt = stmt.where(DiscoveryRun.job_id == job_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    items = db.scalars(stmt.order_by(DiscoveryRun.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": items}


@router.get("/discovery-runs/{run_id}", response_model=DiscoveryRunRead, summary="Dettaglio di una scansione con il log")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(DiscoveryRun, run_id)
    if run is None:
        raise HTTPException(404, "Elemento non trovato")
    return run


@router.get("/discovery-changes/count", response_model=PendingCount, summary="Numero di modifiche da approvare")
def count_pending(db: Session = Depends(get_db)):
    pending = db.scalar(select(func.count(DiscoveryChange.id)).where(DiscoveryChange.status == ChangeStatus.PENDING.value))
    return {"pending": pending or 0}


@router.get("/discovery-changes", response_model=Page[DiscoveryChangeRead], summary="Modifiche proposte dalle scansioni")
def list_changes(
    status: ChangeStatus | None = ChangeStatus.PENDING,
    job_id: int | None = None,
    device_id: int | None = None,
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(DiscoveryChange)
    if status is not None:
        stmt = stmt.where(DiscoveryChange.status == status.value)
    if job_id is not None:
        stmt = stmt.where(DiscoveryChange.job_id == job_id)
    if device_id is not None:
        stmt = stmt.where(DiscoveryChange.device_id == device_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = (DiscoveryChange.device_label, DiscoveryChange.id) if status == ChangeStatus.PENDING else (DiscoveryChange.id.desc(),)
    items = db.scalars(stmt.order_by(*order).limit(limit).offset(offset)).all()
    return {"total": total, "items": items}


@router.post("/discovery-changes/approve", response_model=ApproveResult, summary="Approva e applica le modifiche")
def approve_changes(payload: ChangeIds, db: Session = Depends(get_db)):
    return runner.approve(db, payload.ids)


@router.post("/discovery-changes/reject", response_model=RejectResult,
             summary="Rifiuta le modifiche (con gli stessi dati non verranno riproposte)")
def reject_changes(payload: ChangeIds, db: Session = Depends(get_db)):
    return runner.reject(db, payload.ids)
