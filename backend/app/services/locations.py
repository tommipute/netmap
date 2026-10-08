"""Percorso delle posizioni ("Palazzina A › P1"), salvato in `Location.path` per ordinare, cercare e mostrare.

Ricalcolato prima di ogni flush per le posizioni nuove o modificate e per tutte quelle che contengono:
vale per API, import CSV, scansione e script senza che ognuno se ne debba ricordare.
"""
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models import Location

SEPARATOR = " › "


def location_path(session: Session, loc: Location) -> str:
    names, seen, current = [], set(), loc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        names.append(current.name or "")
        current = session.get(Location, current.parent_id) if current.parent_id else None
    return SEPARATOR.join(reversed(names))


def _refresh(session: Session, loc: Location, seen: set[int]) -> None:
    if id(loc) in seen:  # gerarchia circolare: la rifiuta location_hook, qui basta non girare all'infinito
        return
    seen.add(id(loc))
    path = location_path(session, loc)
    if loc.path != path:
        loc.path = path
    if loc.id is not None:
        for child in session.scalars(select(Location).where(Location.parent_id == loc.id)):
            _refresh(session, child, seen)


@event.listens_for(Session, "before_flush")
def _update_paths(session: Session, flush_context, instances) -> None:
    changed = [o for o in (*session.new, *session.dirty) if isinstance(o, Location) and o not in session.deleted]
    if not changed:
        return
    seen: set[int] = set()
    with session.no_autoflush:
        for loc in changed:
            _refresh(session, loc, seen)
