"""Cifratura dei segreti SNMP (community, chiavi v3) con Fernet.

La chiave arriva da SECRETS_KEY; se manca viene generata una volta e salvata in .secrets_key
(cartella backend, condivisa tra api e worker, esclusa da git). Se la chiave cambia
i segreti già salvati non si leggono più: vanno reinseriti nei profili.
"""
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class SecretError(Exception):
    pass


@lru_cache
def _fernet() -> Fernet:
    key = settings.secrets_key.strip()
    if not key:
        path = settings.secrets_key_file
        try:
            # O_EXCL: se api e worker partono insieme, solo uno dei due scrive la chiave
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(Fernet.generate_key().decode())
        except FileExistsError:
            pass
        with open(path) as f:
            key = f.read().strip()
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise SecretError("SECRETS_KEY non valida: serve una chiave Fernet (44 caratteri base64)") from exc


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise SecretError(
            "Impossibile decifrare un segreto SNMP: la chiave è cambiata, reinserisci community e chiavi nel profilo"
        ) from exc
