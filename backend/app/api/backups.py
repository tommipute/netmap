"""Backup (solo admin): file sul server (scarica, carica, ripristina), copie fuori dal server, chiave dei segreti.

I backup e il ripristino li fa lo script sull'host (updater/updater.sh): qui si chiede, non si tocca il database.
Le destinazioni (CRUD in routes.py) le usa il worker (services/offsite.py); prova ed elenco dei file li fa l'API.
"""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.secrets import SecretError, master_key
from app.database import get_db
from app.models import BackupCopy, BackupTarget, BackupTask, User
from app.schemas.backups import FileName, SecretsKey
from app.services import keys, offsite, updater

router = APIRouter(tags=["Backup"], dependencies=[Depends(require_admin)])


def _local(name: str) -> Path:
    if not offsite.BACKUP_NAME.fullmatch(name):
        raise HTTPException(422, "Nome del file non valido")
    if not offsite.mounted():
        raise HTTPException(409, "La cartella dei backup non è montata nel container (vedi README, Backup)")
    path = offsite.backup_dir() / name
    if not path.is_file():
        raise HTTPException(404, "Backup non trovato")
    return path


def _target(db: Session, target_id: int) -> BackupTarget:
    target = db.get(BackupTarget, target_id)
    if target is None:
        raise HTTPException(404, "Destinazione non trovata")
    return target


def _offsite_error(exc: offsite.OffsiteError) -> HTTPException:
    return HTTPException(502, str(exc))


@router.get("/backups", summary="Copie fuori dal server, richieste in corso, chiave dei segreti")
def overview(db: Session = Depends(get_db)):
    copies: dict[str, list[int]] = {}
    for row in db.scalars(select(BackupCopy)):
        copies.setdefault(row.file, []).append(row.target_id)
    tasks = db.scalars(select(BackupTask).order_by(BackupTask.id.desc()).limit(20)).all()
    return {
        "mounted": offsite.mounted(),
        "copies": copies,
        "tasks": [
            {"id": t.id, "target_id": t.target_id, "action": t.action, "file": t.file, "status": t.status,
             "message": t.message, "requested_by": t.requested_by, "created_at": t.created_at, "finished_at": t.finished_at}
            for t in tasks
        ],
        "secrets": keys.status(db),
    }


@router.get("/backups/files/{name}", summary="Scarica un backup")
def download(name: str):
    return FileResponse(_local(name), media_type="application/octet-stream", filename=name)


@router.put("/backups/upload", status_code=201, summary="Carica un backup (corpo della richiesta = il file)")
async def upload(request: Request, name: str = Query(..., max_length=200)):
    name = Path(name.replace("\\", "/")).name
    if not offsite.BACKUP_NAME.fullmatch(name):
        raise HTTPException(422, "Serve un file .dump fatto da NetMap (pg_dump in formato custom)")
    if not offsite.mounted():
        raise HTTPException(409, "La cartella dei backup non è montata nel container (vedi README, Backup)")
    dest = offsite.imported_name(name)
    if (offsite.backup_dir() / dest).exists():
        raise HTTPException(409, f"Sul server c'è già {dest}")
    # Il corpo arriva a pezzi: lo scrivo man mano senza tenerlo in memoria
    temp = offsite.backup_dir() / f".{dest}.part"
    try:
        with temp.open("wb") as out:
            async for chunk in request.stream():
                out.write(chunk)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    try:
        offsite.publish(temp, dest)
    except offsite.OffsiteError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"file": dest}


@router.post("/backups/restore", status_code=202, summary="Chiede allo script di ripristinare un backup")
def restore(body: FileName, user: User | None = Depends(require_admin)):
    _local(body.file)
    if not updater.mounted():
        raise HTTPException(409, "La cartella dell'updater non è montata nel container api: vedi README, Aggiornamenti automatici")
    return updater.request("restore", user.username if user else None, file=body.file)


@router.get("/backups/secrets-key", summary="Scarica la chiave dei segreti")
def secrets_key():
    name = f"netmap-secrets-{keys.fingerprint()}.key"
    return PlainTextResponse(master_key() + "\n", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/backups/secrets-key/rekey", summary="Ricifra i segreti salvati con la chiave di un altro server")
def rekey(body: SecretsKey, db: Session = Depends(get_db)):
    try:
        return keys.rekey(db, body.key)
    except SecretError as exc:
        raise HTTPException(422, str(exc)) from exc


# ------------------------------------------------------------------------------------------ destinazioni
@router.post("/backup-targets/{target_id}/test", summary="Prova la connessione alla destinazione")
def test_target(target_id: int, db: Session = Depends(get_db)):
    target = _target(db, target_id)
    try:
        return offsite.test(db, target)
    except offsite.OffsiteError as exc:
        raise _offsite_error(exc) from exc


@router.get("/backup-targets/{target_id}/files", summary="Backup presenti sulla destinazione")
def target_files(target_id: int, db: Session = Depends(get_db)):
    target = _target(db, target_id)
    try:
        return offsite.remote_listing(db, target)
    except offsite.OffsiteError as exc:
        raise _offsite_error(exc) from exc


def _task(db: Session, target: BackupTarget, action: str, file: str | None, user: User | None) -> dict:
    task = BackupTask(target_id=target.id, action=action, file=file, requested_by=user.username if user else None,
                      created_at=datetime.now(timezone.utc))
    db.add(task)
    db.commit()
    return {"id": task.id, "status": task.status}


@router.post("/backup-targets/{target_id}/sync", status_code=202, summary="Copia ora i backup che mancano")
def sync_target(target_id: int, db: Session = Depends(get_db), user: User | None = Depends(require_admin)):
    return _task(db, _target(db, target_id), "sync", None, user)


@router.post("/backup-targets/{target_id}/fetch", status_code=202, summary="Riporta sul server un backup della destinazione")
def fetch_from_target(target_id: int, body: FileName, db: Session = Depends(get_db), user: User | None = Depends(require_admin)):
    if not offsite.BACKUP_NAME.fullmatch(body.file):
        raise HTTPException(422, "Nome del file non valido")
    return _task(db, _target(db, target_id), "fetch", body.file, user)


@router.post("/backup-targets/{target_id}/use-key", summary="Ricifra i segreti con una chiave copiata sulla destinazione")
def use_key(target_id: int, body: FileName, db: Session = Depends(get_db)):
    target = _target(db, target_id)
    try:
        key = offsite.read_key(target, body.file)
        return keys.rekey(db, key)
    except offsite.OffsiteError as exc:
        raise _offsite_error(exc) from exc
    except SecretError as exc:
        raise HTTPException(422, str(exc)) from exc
