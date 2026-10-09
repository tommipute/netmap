"""Campi personalizzati definiti dall'amministratore. I valori stanno in `custom_fields` di ogni oggetto
(CustomFieldsMixin); qui c'è come sono fatti: tipo, oggetti a cui si applicano, obbligatorio."""
from sqlalchemy import Boolean, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, JSONType, TimestampMixin


class CustomFieldDefinition(TimestampMixin, Base):
    __tablename__ = "custom_field_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)  # chiave in custom_fields (es. "contratto")
    label: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20), default="text", server_default="text")  # CustomFieldType
    choices: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"))  # per "select"
    object_types: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"))  # "devices"…
    required: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    weight: Mapped[int] = mapped_column(Integer, default=100, server_default="100")  # ordine nei moduli
    description: Mapped[str | None] = mapped_column(Text)
