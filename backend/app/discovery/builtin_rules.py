"""Regole SNMP incluse in NetMap (`builtin_rules.json`, stesso formato del file di export): all'avvio dell'API
(`start.sh`) si aggiungono, si aggiornano o si tolgono così che il database sia uguale al file. L'amministratore può
solo spegnerle (`enabled` resta com'è) e una sua regola vale sempre prima (`snmp_rules.Rule.precision`).

    python -m app.discovery.builtin_rules
"""
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.discovery.snmp_rules import FIELDS
from app.models import SnmpRule
from app.schemas.discovery import SnmpRuleCreate, SnmpRuleFile

logger = logging.getLogger("netmap")
FILE = Path(__file__).with_name("builtin_rules.json")


def load() -> list[SnmpRuleCreate]:
    return SnmpRuleFile.model_validate_json(FILE.read_text(encoding="utf-8")).rules


def sync(db: Session, rules: list[SnmpRuleCreate] | None = None) -> dict[str, int]:
    """Allinea le regole incluse del database a `rules` (di solito il file). Una regola dell'amministratore con lo
    stesso nome vince: quella inclusa non si aggiunge."""
    rules = load() if rules is None else rules
    rows = {row.name.lower(): row for row in db.scalars(select(SnmpRule))}
    counts = {"created": 0, "updated": 0, "deleted": 0, "skipped": 0}
    kept: set[int] = set()
    db.info["audit_source"] = "sistema"
    for rule in rules:
        row = rows.get(rule.name.lower())
        if row is not None and not row.builtin:
            logger.warning("Regola SNMP inclusa «%s» non aggiunta: c'è già una regola con lo stesso nome", rule.name)
            counts["skipped"] += 1
            continue
        if row is None:
            row = SnmpRule(builtin=True, enabled=rule.enabled)
            db.add(row)
            counts["created"] += 1
        for field in FIELDS:
            if field != "enabled":
                setattr(row, field, getattr(rule, field))
        if row.id is not None:
            kept.add(row.id)
            if db.is_modified(row):
                counts["updated"] += 1
    for row in rows.values():
        if row.builtin and row.id not in kept:
            db.delete(row)
            counts["deleted"] += 1
    db.commit()
    return counts


def main() -> None:
    from app.database import SessionLocal

    with SessionLocal() as db:
        counts = sync(db)
    print("Regole SNMP incluse: {created} aggiunte, {updated} aggiornate, {deleted} tolte".format(**counts))


if __name__ == "__main__":
    main()
