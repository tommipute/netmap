"""Chiave dei segreti dopo un ripristino: quali valori cifrati non si leggono più e ricifratura con la chiave vecchia.

Un backup ripristinato su un altro server (o dopo aver perso la chiave) contiene password e community cifrate con la
chiave del vecchio server. Con quella chiave (copiata a mano o dalla destinazione dei backup) si decifrano e si
ricifrano con la chiave di adesso, senza riavviare niente.
"""
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secrets import SecretError, decrypt, encrypt, master_key
from app.models import AlertChannel, BackupTarget, SnmpProfile

# Tutte le colonne cifrate con la chiave dei segreti
ENCRYPTED: dict[type, tuple[str, ...]] = {
    SnmpProfile: ("community_enc", "auth_key_enc", "priv_key_enc"),
    AlertChannel: ("secret_enc",),
    BackupTarget: ("secret_enc", "private_key_enc"),
}


def fingerprint(key: str | None = None) -> str:
    return hashlib.sha256((key or master_key()).encode()).hexdigest()[:12]


def _values(db: Session):
    for model, columns in ENCRYPTED.items():
        for obj in db.scalars(select(model)):
            for column in columns:
                if getattr(obj, column):
                    yield obj, column


def _readable(value: str) -> bool:
    try:
        decrypt(value)
        return True
    except SecretError:
        return False


def status(db: Session) -> dict:
    total = unreadable = 0
    for obj, column in _values(db):
        total += 1
        unreadable += not _readable(getattr(obj, column))
    return {"fingerprint": fingerprint(), "total": total, "unreadable": unreadable}


def rekey(db: Session, old_key: str) -> dict:
    """Ricifra con la chiave di adesso i valori che si leggono con la chiave vecchia."""
    try:
        old = Fernet(old_key.strip().encode())
    except ValueError as exc:
        raise SecretError("La chiave non è valida: serve una chiave di 44 caratteri (il contenuto del file della chiave)") from exc
    fixed = still = 0
    for obj, column in list(_values(db)):
        value = getattr(obj, column)
        if _readable(value):
            continue
        try:
            plain = old.decrypt(value.encode()).decode()
        except InvalidToken:
            still += 1
            continue
        setattr(obj, column, encrypt(plain))
        fixed += 1
    db.commit()
    return {"fixed": fixed, "unreadable": still}
