"""Generatore di endpoint CRUD: elenco con filtri, dettaglio, creazione, modifica (PATCH), eliminazione.

Ogni entità usa lo stesso schema; le regole specifiche stanno negli "hook" (app/services/rules.py).

Oltre ai filtri dichiarati (uguaglianza, compaiono in /docs) l'elenco accetta filtri per colonna generici, usati
dai filtri sotto le intestazioni delle tabelle: `<campo>__contains=testo` (contiene, senza maiuscole),
`<campo>__eq=valore`, `<campo>__isnull=true|false`, e `sort=<campo>` / `sort=-<campo>`. Valgono per le colonne
del modello e per i campi calcolati cercabili (es. management_ip del device); un campo sconosciuto dà 422.
"""
import inspect
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from pydantic import BaseModel
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.base import Base
from app.schemas.common import Page

# hook(db, oggetto, dati_ricevuti, is_create) -> solleva HTTPException se qualcosa non va
Hook = Callable[[Session, Any, dict[str, Any], bool], None]

_table_to_model: dict[str, type] = {}


def _model_for_table(table_name: str) -> type:
    if not _table_to_model:
        for mapper in Base.registry.mappers:
            _table_to_model[mapper.local_table.name] = mapper.class_
    return _table_to_model[table_name]


def check_foreign_keys(db: Session, model: type, data: dict[str, Any]) -> None:
    """Controlla che gli id collegati esistano, con un messaggio chiaro invece di un errore del DB."""
    columns = model.__table__.columns
    for key, value in data.items():
        if value is None or key not in columns:
            continue
        for fk in columns[key].foreign_keys:
            target = _model_for_table(fk.column.table.name)
            if db.get(target, value) is None:
                raise HTTPException(422, f"{key}={value}: elemento collegato non trovato")


def apply_data(model: type, obj: Any, data: dict[str, Any]) -> None:
    columns = model.__table__.columns
    for key, value in data.items():
        if key not in columns:
            continue  # campi extra (es. tagged_vlan_ids) li gestiscono gli hook
        if value is None and not columns[key].nullable:
            raise HTTPException(422, f"Il campo '{key}' non può essere vuoto")
        setattr(obj, key, value)


def _short(exc: Exception) -> str:
    text = str(getattr(exc, "orig", exc)).strip()
    return (text.splitlines() or [""])[0]


def commit_or_error(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409, f"Operazione non consentita: valore duplicato o elemento ancora in uso ({_short(exc)})"
        ) from exc
    except DataError as exc:
        db.rollback()
        raise HTTPException(422, f"Valore non valido ({_short(exc)})") from exc


def column_attribute(model: type, searchable: tuple[str, ...], name: str):
    """Colonna del modello o campo calcolato cercabile (es. management_ip del device); None se non esiste."""
    columns = model.__table__.columns
    if name in columns:
        return columns[name]
    if name in searchable and hasattr(model, name):
        return getattr(model, name)
    return None


def _parse(attr, raw: str):
    try:
        py_type = attr.type.python_type
    except (AttributeError, NotImplementedError):
        return raw
    if py_type is bool:
        if raw.lower() not in ("true", "false", "1", "0"):
            raise HTTPException(422, f"Valore non valido: {raw}")
        return raw.lower() in ("true", "1")
    try:
        return py_type(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"Valore non valido: {raw}") from exc


def apply_column_filters(model: type, searchable: tuple[str, ...], stmt, query_params):
    """Filtri per colonna (<campo>__contains / __eq / __isnull) presi dai parametri della richiesta."""
    for key, raw in query_params.multi_items():
        if "__" not in key:
            continue
        name, op = key.rsplit("__", 1)
        attr = column_attribute(model, searchable, name)
        if attr is None or op not in ("contains", "eq", "isnull"):
            raise HTTPException(422, f"Filtro non valido: {key}")
        if op == "contains":
            if raw.strip():
                stmt = stmt.where(cast(attr, String).ilike(f"%{raw.strip()}%"))
        elif op == "isnull":
            stmt = stmt.where(attr.is_(None) if raw.lower() in ("true", "1") else attr.is_not(None))
        else:
            stmt = stmt.where(attr == _parse(attr, raw))
    return stmt


def build_crud_router(
    *,
    model: type,
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    read_schema: type[BaseModel],
    path: str,
    tag: str,
    filters: tuple[str, ...] = (),
    search: tuple[str, ...] = (),
    order_by: tuple = (),
    hook: Hook | None = None,
    delete_hook: Callable[[Session, Any, dict], None] | None = None,  # riceve anche i parametri della richiesta
    dependencies: list | None = None,
) -> APIRouter:
    router = APIRouter(prefix=path, tags=[tag], dependencies=dependencies or [])
    columns = model.__table__.columns
    ordering = order_by or (model.id,)

    def get_or_404(db: Session, item_id: int):
        obj = db.get(model, item_id)
        if obj is None:
            raise HTTPException(404, "Elemento non trovato")
        return obj

    def sorting(sort: str | None):
        if not sort:
            return ordering
        attr = column_attribute(model, search, sort.lstrip("-"))
        if attr is None:
            raise HTTPException(422, f"Ordinamento non valido: {sort}")
        first = attr.desc().nulls_last() if sort.startswith("-") else attr.asc().nulls_last()
        return (first, *ordering)

    # ----- Elenco: i filtri vengono generati dinamicamente così compaiono anche in /docs -----
    def list_items(**kwargs):
        db: Session = kwargs.pop("db")
        request: Request = kwargs.pop("request")
        limit: int = kwargs.pop("limit")
        offset: int = kwargs.pop("offset")
        sort: str | None = kwargs.pop("sort", None)
        q: str | None = kwargs.pop("q", None)

        stmt = apply_column_filters(model, search, select(model), request.query_params)
        for name, value in kwargs.items():
            if value is not None:
                stmt = stmt.where(columns[name] == value)
        if q and search:
            # Anche campi calcolati (column_property), es. l'IP di management del device
            stmt = stmt.where(or_(*((columns[f] if f in columns else getattr(model, f)).ilike(f"%{q}%") for f in search)))

        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.scalars(stmt.order_by(*sorting(sort)).limit(limit).offset(offset)).all()
        return {"total": total, "items": [read_schema.model_validate(r) for r in rows]}

    kw = inspect.Parameter.KEYWORD_ONLY
    params = [
        inspect.Parameter("db", kw, default=Depends(get_db), annotation=Session),
        inspect.Parameter("request", kw, annotation=Request),
        inspect.Parameter("limit", kw, default=Query(50, ge=1, le=1000), annotation=int),
        inspect.Parameter("offset", kw, default=Query(0, ge=0), annotation=int),
        inspect.Parameter(
            "sort", kw, default=Query(None, description="Campo per l'ordinamento, con - davanti al contrario"),
            annotation=Optional[str],
        ),
    ]
    if search:
        params.append(
            inspect.Parameter(
                "q", kw, default=Query(None, description=f"Cerca in: {', '.join(search)}"), annotation=Optional[str]
            )
        )
    for name in filters:
        py_type = columns[name].type.python_type
        params.append(inspect.Parameter(name, kw, default=Query(None), annotation=Optional[py_type]))
    list_items.__signature__ = inspect.Signature(params)
    router.add_api_route(
        "", list_items, methods=["GET"], response_model=Page[read_schema], summary=f"Elenco ({tag})"
    )

    # ----- Dettaglio -----
    @router.get("/{item_id}", response_model=read_schema, summary=f"Dettaglio ({tag})")
    def get_item(item_id: int, db: Session = Depends(get_db)):
        return read_schema.model_validate(get_or_404(db, item_id))

    # ----- Creazione -----
    @router.post("", response_model=read_schema, status_code=201, summary=f"Crea ({tag})")
    def create_item(payload: create_schema, db: Session = Depends(get_db)):
        data = payload.model_dump()
        check_foreign_keys(db, model, data)
        obj = model()
        apply_data(model, obj, data)
        db.add(obj)
        if hook:
            hook(db, obj, data, True)
        commit_or_error(db)
        db.refresh(obj)
        return read_schema.model_validate(obj)

    # ----- Modifica parziale -----
    @router.patch("/{item_id}", response_model=read_schema, summary=f"Modifica ({tag})")
    def update_item(item_id: int, payload: update_schema, db: Session = Depends(get_db)):
        obj = get_or_404(db, item_id)
        data = payload.model_dump(exclude_unset=True)
        check_foreign_keys(db, model, data)
        apply_data(model, obj, data)
        if hook:
            hook(db, obj, data, False)
        commit_or_error(db)
        db.refresh(obj)
        return read_schema.model_validate(obj)

    # ----- Eliminazione -----
    @router.delete("/{item_id}", status_code=204, response_class=Response, summary=f"Elimina ({tag})")
    def delete_item(item_id: int, request: Request, db: Session = Depends(get_db)):
        obj = get_or_404(db, item_id)
        if delete_hook:
            delete_hook(db, obj, dict(request.query_params))
        db.delete(obj)
        commit_or_error(db)
        return Response(status_code=204)

    return router
