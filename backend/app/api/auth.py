"""Login e permessi (fase 4).

Sessione: token firmato in un cookie httpOnly (il browser lo manda da solo, anche per i download);
script e integrazioni possono usare lo stesso token con "Authorization: Bearer".
Ruoli: viewer = solo lettura, editor = modifica i dati, admin = anche gli utenti.
Al primo avvio, senza utenti, la pagina di login chiede di creare l'amministratore.
Con Active Directory attivo (api/directory.py) chi non ha un utente locale entra con l'utente di dominio: l'utente
NetMap si crea al primo accesso e ruolo e nome si aggiornano a ogni accesso, dai gruppi del dominio.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.auth import create_token, decode_token, hash_password, verify_password
from app.core.throttle import Throttle, client_ip
from app.database import get_db
from app.models import User
from app.services import directory
from app.models.enums import UserRole, UserSource
from app.schemas.auth import AuthStatus, LoginRequest, LoginResult, PasswordChange, SetupRequest, UserRead

COOKIE = "netmap_session"
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
WRITE_ROLES = {UserRole.ADMIN.value, UserRole.EDITOR.value}

# Tentativi sbagliati. Per nome utente: dopo 5 errori si aspetta un minuto, poi ogni errore raddoppia l'attesa
# fino a 15 minuti. Per indirizzo (chi prova tanti nomi diversi): 20 errori in 15 minuti = 15 minuti di blocco.
user_throttle = Throttle(max_failures=5, base_lock=60, max_lock=900, window=900)
ip_throttle = Throttle(max_failures=20, base_lock=900, max_lock=900, window=900)
# Hash di una password a caso: con un nome utente inesistente la verifica dura come con uno vero
_DUMMY_HASH = hash_password("netmap-nessun-utente")
log = logging.getLogger("netmap.auth")

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
    return {"auth_enabled": settings.auth_enabled, "setup_required": settings.auth_enabled and _users_count(db) == 0,
            "directory": settings.auth_enabled and directory.active_settings(db) is not None}


@router.post("/setup", response_model=LoginResult, status_code=201,
             summary="Crea il primo amministratore (solo se non esiste ancora nessun utente)")
def setup(payload: SetupRequest, response: Response, db: Session = Depends(get_db)):
    if _users_count(db) > 0:
        raise HTTPException(409, "Il primo amministratore esiste già: accedi con le tue credenziali")
    user = User(username=payload.username, first_name=payload.first_name, last_name=payload.last_name, role=UserRole.ADMIN.value,
                password_hash=hash_password(payload.password), active=True, token_version=0)
    db.add(user)
    db.flush()
    return _start_session(response, user, db)


def _too_many(seconds: int) -> HTTPException:
    minutes = max(1, -(-seconds // 60))
    text = "un minuto" if minutes == 1 else f"{minutes} minuti"
    return HTTPException(429, f"Troppi tentativi sbagliati: riprova tra {text}", headers={"Retry-After": str(seconds)})


def _failed(username: str, ip: str) -> HTTPException:
    lock = max(user_throttle.failure(username), ip_throttle.failure(ip))
    log.warning("Accesso non riuscito per %r da %s%s", username, ip, f": bloccato per {lock} s" if lock else "")
    return HTTPException(401, "Nome utente o password sbagliati")


def _domain_user(db: Session, cfg, login: str, password: str, username: str, ip: str) -> User:
    """Accesso con Active Directory: l'utente NetMap (source=ad) si crea o si aggiorna con ruolo e nome del dominio."""
    try:
        found = directory.authenticate(cfg, login, password)
    except directory.DirectoryError as exc:
        log.error("Active Directory non disponibile per %r: %s", username, exc)
        raise HTTPException(503, str(exc))
    except directory.LoginDenied as exc:
        # Conta come tentativo sbagliato: AD dà alcuni di questi codici anche con la password sbagliata
        lock = max(user_throttle.failure(username), ip_throttle.failure(ip))
        log.warning("Accesso di dominio negato per %r da %s: %s%s", username, ip, exc, f" (bloccato per {lock} s)" if lock else "")
        raise HTTPException(403, str(exc))
    if found is None:
        raise _failed(username, ip)
    user = db.scalars(select(User).where(User.username == found.username)).first()
    if user is not None and user.source != UserSource.AD.value:
        raise HTTPException(409, f"In NetMap c'è già un utente locale {found.username}: entra con la sua password "
                                 "oppure chiedi a un amministratore di eliminarlo per usare l'utente di dominio")
    db.info["audit_source"] = "directory"  # storico: utente creato o cambiato dall'accesso di dominio
    if found.role is None:
        log.warning("Utente di dominio %r senza gruppi di NetMap", found.username)
        if user is not None:  # tolto dai gruppi: chiudo anche le sessioni aperte
            user.token_version += 1
            db.commit()
        raise HTTPException(403, "Il tuo utente di dominio non è in nessun gruppo di NetMap: chiedi a un amministratore")
    if user is None:
        user = User(username=found.username, password_hash="!ad", source=UserSource.AD.value, active=True,
                    token_version=0, role=found.role, first_name=found.first_name, last_name=found.last_name)
        db.add(user)
        db.flush()
        log.info("Primo accesso dell'utente di dominio %r (%s)", found.username, found.role)
    else:
        user.role = found.role
        if found.first_name or found.last_name:
            user.first_name, user.last_name = found.first_name, found.last_name
    return user


@router.post("/login", response_model=LoginResult, summary="Accedi")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    username = payload.username.strip().lower()
    ip = client_ip(request)
    wait = max(user_throttle.retry_after(username), ip_throttle.retry_after(ip))
    if wait:
        raise _too_many(wait)

    user = db.scalars(select(User).where(User.username == username)).first()
    cfg = directory.active_settings(db) if settings.auth_enabled else None
    if cfg is not None and (user is None or user.source == UserSource.AD.value):
        user = _domain_user(db, cfg, payload.username, payload.password, username, ip)
    else:
        valid = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)
        if user is None or not valid:
            raise _failed(username, ip)
    if not user.active:
        db.commit()  # ruolo e nome aggiornati dal dominio restano
        raise HTTPException(403, "Utente disattivato: chiedi a un amministratore")
    user_throttle.success(username)
    log.info("Accesso di %r da %s%s", user.username, ip, " (Active Directory)" if user.source == UserSource.AD.value else "")
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
    if user.source == UserSource.AD.value:
        raise HTTPException(422, "La password degli utenti di dominio si cambia in Windows (Active Directory), non qui")
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(422, "La password attuale non è corretta")
    user.password_hash = hash_password(payload.new_password)
    user.token_version += 1  # le altre sessioni aperte scadono
    return _start_session(response, user, db)
