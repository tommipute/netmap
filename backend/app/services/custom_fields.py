"""Campi personalizzati: controllo dei valori, espressioni per filtri, ordinamento e ricerca.

Le definizioni (CustomFieldDefinition) dicono quali chiavi di `custom_fields` hanno un tipo; le chiavi senza
definizione (es. arrivate da un import) restano libere com'erano.
"""
import re
from datetime import date

from fastapi import HTTPException
from sqlalchemy import Text, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import FunctionElement

from app.models import (
    VLAN,
    VRF,
    Cable,
    CustomFieldDefinition,
    Device,
    DeviceType,
    Interface,
    IPAddress,
    Location,
    Prefix,
    Rack,
    Site,
)

# Oggetti che possono avere campi personalizzati: nome usato nelle definizioni (= percorso dell'API) -> modello
OBJECT_TYPES = {
    "devices": Device, "interfaces": Interface, "cables": Cable, "sites": Site, "locations": Location,
    "racks": Rack, "device-types": DeviceType, "prefixes": Prefix, "ip-addresses": IPAddress, "vlans": VLAN,
    "vrfs": VRF,
}
PREFIX = "cf_"  # nei filtri e nell'ordinamento degli elenchi: cf_<nome>__contains, sort=cf_<nome>
_URL = re.compile(r"^https?://\S+$", re.IGNORECASE)


def definitions(db: Session, object_type: str) -> list[CustomFieldDefinition]:
    rows = db.scalars(select(CustomFieldDefinition).order_by(CustomFieldDefinition.weight, CustomFieldDefinition.label))
    return [d for d in rows if object_type in (d.object_types or [])]


def _convert(definition: CustomFieldDefinition, value):
    """Valore pulito secondo il tipo; solleva ValueError con il motivo."""
    kind = definition.type
    if kind == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("true", "1", "sì", "si", "yes"):
            return True
        if text in ("false", "0", "no"):
            return False
        raise ValueError("serve sì o no")
    if kind == "number":
        if isinstance(value, bool):
            raise ValueError("serve un numero")
        try:
            number = float(str(value).strip().replace(",", "."))
        except ValueError:
            raise ValueError("serve un numero") from None
        return int(number) if number.is_integer() else number
    text = str(value).strip()
    if kind == "date":
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise ValueError("serve una data (AAAA-MM-GG)") from None
    if kind == "select":
        if text not in (definition.choices or []):
            raise ValueError(f"valori ammessi: {', '.join(definition.choices or [])}")
        return text
    if kind == "url" and not _URL.match(text):
        raise ValueError("serve un indirizzo che inizia con http:// o https://")
    return text


def clean_values(db: Session, object_type: str, values: dict | None) -> dict:
    """Controlla i campi definiti per quell'oggetto: tipo, valori ammessi, obbligatori. I vuoti si tolgono."""
    result = dict(values or {})
    for definition in definitions(db, object_type):
        value = result.get(definition.name)
        if value is None or (isinstance(value, str) and not value.strip()):
            result.pop(definition.name, None)
            if definition.required:
                raise HTTPException(422, f"Il campo '{definition.label}' è obbligatorio")
            continue
        try:
            result[definition.name] = _convert(definition, value)
        except ValueError as exc:
            raise HTTPException(422, f"Campo '{definition.label}': {exc}") from None
    return result


def column_expressions(db: Session, model: type, object_type: str) -> dict:
    """cf_<nome> -> espressione SQL del valore, con il tipo giusto per confronti e ordinamento."""
    out = {}
    for definition in definitions(db, object_type):
        value = model.custom_fields[definition.name]
        if definition.type == "number":
            out[PREFIX + definition.name] = value.as_float()
        elif definition.type == "bool":
            out[PREFIX + definition.name] = value.as_boolean()
        else:
            out[PREFIX + definition.name] = value.as_string()
    return out


class values_text(FunctionElement):
    """Tutti i valori di un campo JSON (custom_fields) uniti in un testo, per la ricerca (le chiavi no)."""

    type = Text()
    inherit_cache = True


@compiles(values_text)
def _values_text(element, compiler, **kw):  # SQLite (test)
    column = compiler.process(list(element.clauses)[0], **kw)
    return f"(SELECT group_concat(value, ' ') FROM json_each({column}))"


@compiles(values_text, "postgresql")
def _values_text_postgresql(element, compiler, **kw):
    column = compiler.process(list(element.clauses)[0], **kw)
    return f"(SELECT string_agg(value, ' ') FROM jsonb_each_text({column}))"


def search_clause(model: type, like: str):
    """Condizione "un campo personalizzato contiene il testo" (like già con i %)."""
    return values_text(model.custom_fields).ilike(like)
