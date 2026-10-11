"""Integrazioni con altri programmi: token API (gli altri leggono o scrivono NetMap) e webhook (NetMap avvisa gli
altri quando cambia qualcosa)."""
import json
from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.secrets import SecretError, decrypt
from app.models.base import Base, JSONType, TimestampMixin


class ApiToken(TimestampMixin, Base):
    """Token di lunga durata per script e altri programmi: agisce come il suo utente (al massimo con i suoi permessi).

    Del token si salva solo l'hash SHA-256: il testo intero si vede una volta sola, alla creazione."""

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))  # inizio del token, per riconoscerlo negli elenchi
    read_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # vuoto = non scade
    # token_version dell'utente alla creazione: cambio password o disattivazione invalidano anche i token
    user_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_ip: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)

    user = relationship("User", lazy="joined")


class Webhook(TimestampMixin, Base):
    """Indirizzo a cui NetMap manda le modifiche (righe dello storico) appena succedono, a gruppi."""

    __tablename__ = "webhooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    url_enc: Mapped[str | None] = mapped_column(Text)  # cifrato: spesso contiene una chiave
    secret_enc: Mapped[str | None] = mapped_column(Text)  # chiave della firma HMAC (facoltativa), cifrata
    headers_enc: Mapped[str | None] = mapped_column(Text)  # intestazioni in più {nome: valore} (es. Authorization), JSON cifrato
    # Cosa mandare: tipi di oggetto dello storico (device, cable, ip…) e azioni (create, update, delete); vuoto = tutto
    object_types: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    actions: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    verify_tls: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Ultima riga dello storico già mandata (o saltata): si riparte da lì, anche dopo un errore o un riavvio
    cursor: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Buchi negli id sotto il cursore [da, a, quando visti]: righe di transazioni ancora aperte (un import lungo)
    # che arrivano dopo; si ricontrollano per qualche ora, poi si lasciano (transazione annullata)
    gaps: Mapped[list] = mapped_column(JSONType, default=list, server_default="[]")
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)

    @property
    def has_secret(self) -> bool:
        return bool(self.secret_enc)

    def header_values(self) -> dict[str, str]:
        """Intestazioni in più, decifrate (SecretError se la chiave non le legge)."""
        return json.loads(decrypt(self.headers_enc)) if self.headers_enc else {}

    @property
    def headers(self) -> dict[str, str]:
        """Da mostrare: solo i nomi, i valori restano segreti."""
        try:
            return {name: "" for name in self.header_values()}
        except (SecretError, ValueError):
            return {}

    @property
    def url_host(self) -> str | None:
        """Solo il server dell'indirizzo, da mostrare: il resto può contenere una chiave."""
        try:
            return urlsplit(decrypt(self.url_enc)).hostname if self.url_enc else None
        except (SecretError, ValueError):
            return None
