"""Password e token di sessione (JWT HS256) senza librerie esterne.

Password: scrypt con sale casuale, salvata come "scrypt$n$r$p$sale$hash".
Token: JWT firmato con una chiave ricavata da AUTH_SECRET oppure dalla chiave dei segreti SNMP.
"""
import base64
import hashlib
import hmac
import json
import secrets as pysecrets
import time
from functools import lru_cache

from app.config import settings
from app.core.secrets import master_key

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = pysecrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        computed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                  dklen=len(digest) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(computed.hex(), digest)


@lru_cache
def _signing_key() -> bytes:
    base = settings.auth_secret.strip() or master_key()
    return hmac.new(base.encode(), b"netmap-session-token", hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(user_id: int, version: int, hours: int | None = None) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(json.dumps(
        {"sub": str(user_id), "ver": version, "iat": now, "exp": now + 3600 * (hours or settings.session_hours)},
        separators=(",", ":"),
    ).encode())
    signature = hmac.new(_signing_key(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def decode_token(token: str) -> dict | None:
    """Payload del token se firma e scadenza sono valide, altrimenti None."""
    try:
        header, payload, signature = token.split(".")
        expected = hmac.new(_signing_key(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        if json.loads(_unb64(header)).get("alg") != "HS256":
            return None
        data = json.loads(_unb64(payload))
        if int(data.get("exp", 0)) < time.time():
            return None
        return data
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
