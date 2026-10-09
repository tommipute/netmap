"""Import da NetBox (solo admin): prova della connessione qui, l'import lo fa il worker (services/netbox.py)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.secrets import encrypt
from app.database import get_db
from app.models import ImportRun, User
from app.models.enums import RunStatus
from app.schemas.netbox import ImportRunRead, ImportRunSummary, NetBoxConnection, NetBoxImportCreate, NetBoxProbe
from app.services import netbox

router = APIRouter(tags=["Import da NetBox"], dependencies=[Depends(require_admin)])


@router.post("/netbox/test", response_model=NetBoxProbe,
             summary="Prova la connessione a NetBox: versione, quanti oggetti ci sono, sedi da scegliere")
def test_connection(payload: NetBoxConnection):
    try:
        return netbox.probe(netbox.Client(payload.url, payload.token, payload.verify_tls))
    except netbox.NetBoxError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/netbox/imports", response_model=list[ImportRunSummary], summary="Ultimi import da NetBox")
def list_imports(db: Session = Depends(get_db)):
    return db.scalars(select(ImportRun).order_by(ImportRun.id.desc()).limit(netbox.KEEP_RUNS)).all()


@router.get("/netbox/imports/{run_id}", response_model=ImportRunRead, summary="Stato, log e problemi di un import")
def get_import(run_id: int, db: Session = Depends(get_db)):
    run = db.get(ImportRun, run_id)
    if run is None:
        raise HTTPException(404, "Import non trovato")
    return run


@router.post("/netbox/imports", response_model=ImportRunRead, status_code=201,
             summary="Mette in coda un import (o una simulazione) da NetBox: lo esegue il worker")
def create_import(payload: NetBoxImportCreate, db: Session = Depends(get_db),
                  user: User | None = Depends(require_admin)):
    try:
        url = netbox.normalize_url(payload.url)
    except netbox.NetBoxError as exc:
        raise HTTPException(422, str(exc)) from exc
    if netbox.active_run(db) is not None:
        raise HTTPException(409, "C'è già un import da NetBox in corso: aspetta che finisca")
    run = ImportRun(
        url=url, token_enc=encrypt(payload.token.strip()), verify_tls=payload.verify_tls,
        site_ids=sorted(set(payload.site_ids)), site_names=[], dry_run=payload.dry_run,
        status=RunStatus.QUEUED.value, counts={}, problems=[], log="",
        requested_by_id=user.id if user else None, requested_by=user.username if user else None,
    )
    db.add(run)
    db.flush()
    netbox.prune(db)
    db.commit()
    return run
