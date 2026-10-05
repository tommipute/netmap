from datetime import datetime

from sqlalchemy import JSON, DateTime, MetaData, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.models.enums import Source

# Nomi dei vincoli prevedibili -> migration Alembic più pulite
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CustomFieldsMixin:
    """Campi personalizzati liberi (chiave/valore)."""

    custom_fields: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"))


class DiscoveryMixin:
    """Da dove arriva il dato (manuale / SNMP) e quando la scansione l'ha visto l'ultima volta.
    Servirà in fase 3 per non sovrascrivere i dati inseriti a mano."""

    source: Mapped[str] = mapped_column(
        String(20), default=Source.MANUAL.value, server_default=Source.MANUAL.value
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
