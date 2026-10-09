from enum import StrEnum

from pydantic import Field

from app.schemas.common import InputSchema, Name, ReadSchema, make_partial


class CustomFieldType(StrEnum):
    TEXT = "text"
    LONGTEXT = "longtext"
    NUMBER = "number"
    BOOL = "bool"
    DATE = "date"
    SELECT = "select"
    URL = "url"


class CustomFieldBase(InputSchema):
    name: str = Field(..., max_length=50, pattern=r"^[a-z][a-z0-9_]*$",
                      description="Chiave in custom_fields: minuscole, cifre e _ (es. contratto)")
    label: Name
    type: CustomFieldType = CustomFieldType.TEXT
    choices: list[str] = Field(default_factory=list, description="Valori ammessi (tipo select)")
    object_types: list[str] = Field(default_factory=list, description="Oggetti che lo hanno (devices, sites…)")
    required: bool = False
    weight: int = Field(100, ge=0, le=10000, description="Ordine nei moduli (prima i numeri bassi)")
    description: str | None = None


class CustomFieldCreate(CustomFieldBase):
    pass


CustomFieldUpdate = make_partial(CustomFieldBase, "CustomFieldUpdate")


class CustomFieldRead(CustomFieldBase, ReadSchema):
    pass
