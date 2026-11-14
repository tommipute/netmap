"""Regole SNMP (solo admin): export e import del file delle regole, prova di una regola su un indirizzo.
Elenco, creazione, modifica ed eliminazione sono gli endpoint CRUD standard (registrati in routes.py)."""
import copy
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.database import get_db
from app.discovery import runner, snmp, snmp_rules
from app.discovery.report import build_report
from app.discovery.targets import TargetError, expand_targets
from app.models import Device, SnmpRule
from app.schemas.discovery import SnmpRuleFile, SnmpRuleImportResult, SnmpRuleTest, SnmpRuleTestResult
from app.services.rules import snmp_rule_hook

router = APIRouter(tags=["Scansione"], dependencies=[Depends(require_admin)])

FIELDS = snmp_rules.FIELDS


def filter_devices(db: Session, stmt, rule_id: int):
    """Filtro `snmp_rule` dell'elenco dei device (e del loro export): quelli a cui la regola vale adesso."""
    row = db.get(SnmpRule, rule_id)
    return stmt.where(Device.id.in_(runner.rule_devices(db, [row])[row.id] if row else []))


@router.get("/snmp-rules/usage", response_model=dict[int, int],
            summary="Per ogni regola quanti device ha trovato (dall'ultima lettura di ciascuno, anche se è spenta)")
def rules_usage(db: Session = Depends(get_db)):
    return {rule_id: len(ids) for rule_id, ids in runner.rule_devices(db, list(db.scalars(select(SnmpRule)))).items()}


@router.get("/snmp-rules/export", response_model=SnmpRuleFile,
            summary="Le regole SNMP scritte qui (non quelle incluse in NetMap) in un file JSON, da importare altrove")
def export_rules(db: Session = Depends(get_db)):
    rows = db.scalars(select(SnmpRule).where(SnmpRule.builtin.is_(False)).order_by(SnmpRule.name)).all()
    return {"rules": [{key: getattr(row, key) for key in FIELDS} for row in rows]}


@router.post("/snmp-rules/import", response_model=SnmpRuleImportResult,
             summary="Importa un file di regole: quelle con lo stesso nome si aggiornano, le altre si aggiungono")
def import_rules(payload: SnmpRuleFile, db: Session = Depends(get_db)):
    existing = {row.name.lower(): row for row in db.scalars(select(SnmpRule))}
    created = updated = 0
    seen: set[str] = set()
    for rule in payload.rules:
        key = rule.name.lower()
        if key in seen:
            raise HTTPException(422, f"Il file contiene due regole «{rule.name}»")
        seen.add(key)
        row = existing.get(key)
        if row is not None and row.builtin:
            db.rollback()
            raise HTTPException(422, f"«{rule.name}» è il nome di una regola inclusa in NetMap: cambia il nome nel file")
        if row is None:
            row = SnmpRule()
            db.add(row)
            created += 1
        else:
            updated += 1
        for field in FIELDS:
            setattr(row, field, getattr(rule, field))
        try:
            snmp_rule_hook(db, row, rule.model_dump(), row.id is None)
        except HTTPException as exc:
            db.rollback()
            raise HTTPException(422, f"Regola «{rule.name}»: {exc.detail}") from exc
    db.commit()
    return {"created": created, "updated": updated}


def _rule_from(payload: SnmpRuleTest) -> snmp_rules.Rule:
    fields = payload.rule.model_dump()
    return snmp_rules.compile_rule(SimpleNamespace(**fields, id=payload.rule_id or 2**31))


def _variant(raw: snmp.HostData, rules: list[snmp_rules.Rule]) -> snmp.HostData:
    data = copy.deepcopy(raw)
    data.notes = dict(data.notes)
    matched = snmp_rules.matching(rules, data.sys_object_id, data.sys_descr)
    if matched:
        snmp_rules.apply(data, matched, raw.rule_values)
    return data


@router.post("/snmp-rules/test", response_model=SnmpRuleTestResult,
             summary="Prova una regola (anche non salvata) su un indirizzo: cosa si legge prima e dopo")
def test_rule(payload: SnmpRuleTest, db: Session = Depends(get_db)):
    try:
        [host] = expand_targets([payload.host.strip()], 1)
    except (TargetError, ValueError) as exc:
        raise HTTPException(422, "Scrivi un solo indirizzo IP") from exc
    credentials = runner.load_credentials(db, payload.profile_ids)
    if not credentials:
        raise HTTPException(422, "Scegli almeno un profilo SNMP valido")
    snmp_rule_hook(db, payload.rule, payload.rule.model_dump(), True)
    saved = [snmp_rules.compile_rule(r) for r in runner.load_rules(db) if r.id != payload.rule_id]
    draft = _rule_from(payload)
    [result] = snmp.probe_all([host], credentials, 1, ping=False, rules=[*saved, draft], apply_rules=False)
    if result.data is None:
        attempts = [{"profile": a.profile, "error": a.error, "answered": a.answered} for a in result.attempts]
        return {"host": host, "error": result.error, "attempts": attempts}
    raw = result.data
    before, after = _variant(raw, saved), _variant(raw, [*saved, draft])
    names = {i.if_index: i.name for i in after.interfaces}
    return {
        "host": host,
        "matches": draft.matches(raw.sys_object_id, raw.sys_descr),
        "before": build_report(before),
        "after": build_report(after),
        "ports": [{"if_index": i.if_index, "before": i.name, "after": names.get(i.if_index)}
                  for i in before.interfaces if names.get(i.if_index) != i.name],
    }
