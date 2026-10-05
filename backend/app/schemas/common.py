import re
from datetime import datetime
from typing import Annotated, Any, Generic, Optional, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, create_model

from app.core.net import normalize_ip_interface, normalize_mac, normalize_prefix

T = TypeVar("T")
_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _not_blank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("Il campo non può essere vuoto")
    return value


def _color(value: str) -> str:
    if not _COLOR_RE.match(value):
        raise ValueError("Colore non valido, usa il formato #RRGGBB")
    return value.upper()


# Tipi riutilizzabili con validazione/normalizzazione
Name = Annotated[str, AfterValidator(_not_blank), Field(max_length=100)]
HexColor = Annotated[str, AfterValidator(_color)]
MacAddress = Annotated[str, AfterValidator(normalize_mac)]
PrefixStr = Annotated[str, AfterValidator(normalize_prefix)]
IPInterfaceStr = Annotated[str, AfterValidator(normalize_ip_interface)]


class InputSchema(BaseModel):
    model_config = ConfigDict(use_enum_values=True, extra="forbid", validate_default=True)


class ReadSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DiscoveryRead(BaseModel):
    source: str = "manual"
    last_seen_at: datetime | None = None


class Page(BaseModel, Generic[T]):
    total: int
    items: list[T]


def make_partial(schema: type[BaseModel], name: str) -> type[BaseModel]:
    """Crea la versione PATCH di uno schema: tutti i campi opzionali, validazioni mantenute."""
    fields: dict[str, Any] = {}
    for field_name, field in schema.model_fields.items():
        annotation = field.annotation
        if field.metadata:
            annotation = Annotated[(annotation, *field.metadata)]
        fields[field_name] = (Optional[annotation], Field(None, description=field.description))
    return create_model(name, __base__=InputSchema, **fields)
