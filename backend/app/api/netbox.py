"""Import da NetBox e dagli altri programmi (solo admin): la prova della connessione gira qui, l'import lo fa il
worker (services/netbox.py, services/connectors.py). /netbox/* resta per compatibilità; la pagina usa /imports."""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.secrets import encrypt
from app.database import get_db
from app.models import ImportRun, User
from app.models.enums import RunStatus
from app.schemas.netbox import (
    ImportRunRead,
    ImportRunSummary,
    NetBoxConnection,
    NetBoxImportCreate,
    NetBoxProbe,
    SourceConnection,
    SourceImportCreate,
    SourceProbe,
)
from app.services import netbox

router = APIRouter(tags=["Import da altri programmi"], dependencies=[Depends(require_admin)])


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


def _secrets(payload: SourceConnection) -> dict:
    secrets = {"token": payload.token.strip()}
    if payload.app_token and payload.app_token.strip():
        secrets["app_token"] = payload.app_token.strip()
    return secrets


def _open(payload: SourceConnection):
    try:
        return netbox.open_source(payload.source, payload.url, _secrets(payload), payload.username,
                                  payload.verify_tls)
    except netbox.SourceError as exc:
        raise HTTPException(422, str(exc)) from exc


def _queue(db: Session, user: User | None, payload: SourceConnection, group_ids: list, default_site: str | None,
           dry_run: bool) -> ImportRun:
    source = _open(payload)  # controlla l'indirizzo
    url = source.client.base if payload.source == "netbox" else payload.url.strip().rstrip("/")
    if netbox.active_run(db) is not None:
        raise HTTPException(409, "C'è già un import in corso: aspetta che finisca")
    run = ImportRun(
        source=payload.source, url=url, token_enc=encrypt(json.dumps(_secrets(payload))),
        username=(payload.username or "").strip() or None, verify_tls=payload.verify_tls,
        default_site=(default_site or "").strip() or None,
        site_ids=sorted(set(group_ids), key=lambda g: (isinstance(g, str), g)), site_names=[], dry_run=dry_run,
        status=RunStatus.QUEUED.value, counts={}, problems=[], log="",
        requested_by_id=user.id if user else None, requested_by=user.username if user else None,
    )
    db.add(run)
    db.flush()
    netbox.prune(db)
    db.commit()
    return run


@router.post("/netbox/imports", response_model=ImportRunRead, status_code=201,
             summary="Mette in coda un import (o una simulazione) da NetBox: lo esegue il worker")
def create_import(payload: NetBoxImportCreate, db: Session = Depends(get_db),
                  user: User | None = Depends(require_admin)):
    connection = SourceConnection(source="netbox", url=payload.url, token=payload.token, verify_tls=payload.verify_tls)
    return _queue(db, user, connection, payload.site_ids, None, payload.dry_run)


@router.post("/imports/test", response_model=SourceProbe,
             summary="Prova la connessione: versione, quanti device ci sono, sedi o gruppi da scegliere")
def test_source(payload: SourceConnection):
    source = _open(payload)
    try:
        return source.probe()
    except netbox.SourceError as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        try:
            source.close()
        except netbox.SourceError:
            pass


@router.get("/imports", response_model=list[ImportRunSummary], summary="Ultimi import da altri programmi")
def list_source_imports(db: Session = Depends(get_db)):
    return list_imports(db)


@router.get("/imports/{run_id}", response_model=ImportRunRead, summary="Stato, log e problemi di un import")
def get_source_import(run_id: int, db: Session = Depends(get_db)):
    return get_import(run_id, db)


@router.post("/imports", response_model=ImportRunRead, status_code=201,
             summary="Mette in coda un import (o una simulazione): lo esegue il worker")
def create_source_import(payload: SourceImportCreate, db: Session = Depends(get_db),
                         user: User | None = Depends(require_admin)):
    connection = SourceConnection(**payload.model_dump(include=set(SourceConnection.model_fields)))
    return _queue(db, user, connection, payload.group_ids, payload.default_site, payload.dry_run)
