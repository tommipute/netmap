"""Login e permessi (fase 4).

Sessione: token firmato in un cookie httpOnly (il browser lo manda da solo, anche per i download);
script e integrazioni possono usare lo stesso token con "Authorization: Bearer".
Ruoli: viewer = solo lettura, editor = modifica i dati, admin = anche gli utenti.
Al primo avvio, senza utenti, la pagina di login chiede di creare l'amministratore.
"""
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import create_token, decode_token, hash_password, verify_password
from app.database import get_db
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import AuthStatus, LoginRequest, LoginResult, PasswordChange, SetupRequest, UserRead

COOKIE = "netmap_session"
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
WRITE_ROLES = {UserRole.ADMIN.value, UserRole.EDITOR.value}

# Tentativi sbagliati per nome utente: dopo 5 errori si aspetta un minuto
MAX_FAILURES, LOCK_SECONDS = 5, 60
_failures: dict[str, list[float]] = defaultdict(list)

router = APIRouter(prefix="/auth", tags=["Login"])


# ---------------------------------------------------------------- dipendenze
def _token_from(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(COOKIE)


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Utente della richiesta; 401 se manca o non è valido. Con il login disattivato restituisce None."""
    if not settings.auth_enabled:
        return None
    token = _token_from(request)
    data = decode_token(token) if token else None
    user = db.get(User, int(data["sub"])) if data and str(data.get("sub", "")).isdigit() else None
    if user is None or not user.active or data.get("ver") != user.token_version:
        raise HTTPException(401, "Sessione scaduta o non valida: accedi di nuovo", headers={"WWW-Authenticate": "Bearer"})
    request.state.user = user
    db.info["audit_user"] = (user.id, user.username)  # chi fa le modifiche: services/audit.py
    return user


def require_user(request: Request, user: User | None = Depends(current_user)) -> User | None:
    """Tutti gli utenti leggono; per scrivere serve il ruolo editor o admin."""
    if user is not None and request.method not in READ_METHODS and user.role not in WRITE_ROLES:
        raise HTTPException(403, "Il tuo utente può solo consultare i dati: chiedi a un amministratore di cambiarti il ruolo")
    return user


def require_admin(user: User | None = Depends(current_user)) -> User | None:
    if user is not None and user.role != UserRole.ADMIN.value:
        raise HTTPException(403, "Solo gli amministratori possono gestire gli utenti")
    return user


# ---------------------------------------------------------------- sessione
def _start_session(response: Response, user: User, db: Session) -> dict:
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = create_token(user.id, user.token_version)
    response.set_cookie(
        COOKIE, token, max_age=settings.session_hours * 3600, httponly=True, samesite="lax",
        secure=settings.cookie_secure, path="/",
    )
    return {"user": UserRead.model_validate(user), "token": token}


def _users_count(db: Session) -> int:
    return db.scalar(select(func.count(User.id))) or 0


@router.get("/status", response_model=AuthStatus, summary="Login attivo? Serve creare il primo amministratore?")
def auth_status(db: Session = Depends(get_db)):
    return {"auth_enabled": settings.auth_enabled, "setup_required": settings.auth_enabled and _users_count(db) == 0}


@router.post("/setup", response_model=LoginResult, status_code=201,
             summary="Crea il primo amministratore (solo se non esiste ancora nessun utente)")
def setup(payload: SetupRequest, response: Response, db: Session = Depends(get_db)):
    if _users_count(db) > 0:
        raise HTTPException(409, "Il primo amministratore esiste già: accedi con le tue credenziali")
    user = User(username=payload.username, full_name=payload.full_name, role=UserRole.ADMIN.value,
                password_hash=hash_password(payload.password), active=True, token_version=0)
    db.add(user)
    db.flush()
    return _start_session(response, user, db)


@router.post("/login", response_model=LoginResult, summary="Accedi")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    now = time.monotonic()
    recent = [t for t in _failures[username] if now - t < LOCK_SECONDS]
    _failures[username] = recent
    if len(recent) >= MAX_FAILURES:
        raise HTTPException(429, "Troppi tentativi sbagliati: riprova tra un minuto")

    user = db.scalars(select(User).where(User.username == username)).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        recent.append(now)
        raise HTTPException(401, "Nome utente o password sbagliati")
    if not user.active:
        raise HTTPException(403, "Utente disattivato: chiedi a un amministratore")
    _failures.pop(username, None)
    return _start_session(response, user, db)


@router.post("/logout", status_code=204, response_class=Response, summary="Esci")
def logout():
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, path="/")
    return response


@router.get("/me", response_model=UserRead, summary="Utente collegato")
def me(user: User | None = Depends(current_user)):
    if user is None:
        raise HTTPException(404, "Login disattivato (AUTH_ENABLED=false)")
    return user


@router.post("/password", response_model=LoginResult, summary="Cambia la propria password")
def change_password(payload: PasswordChange, response: Response, user: User | None = Depends(current_user),
                    db: Session = Depends(get_db)):
    if user is None:
        raise HTTPException(404, "Login disattivato (AUTH_ENABLED=false)")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(422, "La password attuale non è corretta")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1  # le altre sessioni aperte scadono
    return _start_session(response, user, db)
