"""Integrazioni: token API (ognuno gestisce i suoi, l'amministratore tutti) e prova dei webhook delle modifiche.

I webhook sono un CRUD in routes.py; l'invio lo fa il worker (services/webhooks.py)."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import no_api_token, require_admin
from app.core.auth import API_TOKEN_PREFIX, as_utc, hash_api_token, new_api_token
from app.database import get_db
from app.models import ApiToken, User, Webhook
from app.models.enums import UserRole
from app.schemas.integrations import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from app.services.webhooks import WebhookError, send_test

# Fuori dal router protetto: anche un utente in sola lettura si crea i suoi token (valgono con i suoi permessi)
tokens = APIRouter(tags=["Integrazioni"], dependencies=[Depends(no_api_token)])
router = APIRouter(tags=["Integrazioni"])


def _is_admin(user: User | None) -> bool:
    return user is None or user.role == UserRole.ADMIN.value  # login spento = tutto permesso


def _read(row: ApiToken, token: str | None = None) -> dict:
    data = {
        "id": row.id, "name": row.name, "prefix": row.prefix, "user_id": row.user_id, "username": row.user.username,
        "user_role": row.user.role, "read_only": row.read_only, "expires_at": row.expires_at,
        "expired": bool(row.expires_at and as_utc(row.expires_at) < datetime.now(timezone.utc)),
        "last_used_at": row.last_used_at, "last_used_ip": row.last_used_ip, "description": row.description,
        "created_at": row.created_at,
    }
    if token:
        data["token"] = token
    return data


@tokens.get("/api-tokens", response_model=list[ApiTokenRead], summary="Token API (i propri; l'amministratore tutti)")
def list_tokens(user: User | None = Depends(no_api_token), db: Session = Depends(get_db)):
    stmt = select(ApiToken).order_by(ApiToken.name, ApiToken.id)
    if not _is_admin(user):
        stmt = stmt.where(ApiToken.user_id == user.id)
    return [_read(row) for row in db.scalars(stmt).unique()]


@tokens.post("/api-tokens", response_model=ApiTokenCreated, status_code=201,
             summary="Crea un token API (il testo intero si vede solo nella risposta)")
def create_token(payload: ApiTokenCreate, user: User | None = Depends(no_api_token), db: Session = Depends(get_db)):
    owner_id = payload.user_id or (user.id if user else None)
    if owner_id is None:
        raise HTTPException(422, "Scegli l'utente del token")
    if user is not None and owner_id != user.id and not _is_admin(user):
        raise HTTPException(403, "Solo gli amministratori creano token per altri utenti")
    owner = db.get(User, owner_id)
    if owner is None:
        raise HTTPException(422, "Utente non trovato")
    if not owner.active:
        raise HTTPException(422, "L'utente è disattivato")
    token = new_api_token()
    row = ApiToken(
        user_id=owner.id, name=payload.name.strip(), token_hash=hash_api_token(token),
        prefix=token[:len(API_TOKEN_PREFIX) + 6], read_only=payload.read_only, user_version=owner.token_version,
        expires_at=datetime.now(timezone.utc) + timedelta(days=payload.expires_days) if payload.expires_days else None,
        description=payload.description,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _read(row, token)


@tokens.delete("/api-tokens/{token_id}", status_code=204, summary="Revoca un token API")
def delete_token(token_id: int, user: User | None = Depends(no_api_token), db: Session = Depends(get_db)):
    row = db.get(ApiToken, token_id)
    if row is None or (not _is_admin(user) and row.user_id != user.id):
        raise HTTPException(404, "Token non trovato")
    db.delete(row)
    db.commit()


@router.post("/webhooks/{webhook_id}/test", summary="Manda una modifica di prova", dependencies=[Depends(require_admin)])
def test_webhook(webhook_id: int, db: Session = Depends(get_db)):
    hook = db.get(Webhook, webhook_id)
    if hook is None:
        raise HTTPException(404, "Webhook non trovato")
    try:
        send_test(hook)
    except WebhookError as exc:
        raise HTTPException(502, f"Invio non riuscito: {exc}") from exc
    return {"ok": True}
