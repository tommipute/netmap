#!/bin/sh
set -e

# Le migration stanno in alembic/versions (le genera chi sviluppa, vedi README): mai crearle qui all'avvio
if ! ls alembic/versions/*.py >/dev/null 2>&1; then
  echo "Nessuna migration in alembic/versions: il codice è incompleto, l'API non parte." >&2
  exit 1
fi

# Applica solo quelle mancanti (già fatte = niente da fare); se una fallisce l'API non parte e l'updater torna indietro
alembic upgrade head
# Regole SNMP incluse in NetMap (app/discovery/builtin_rules.json): un errore qui non deve fermare l'API
python -m app.discovery.builtin_rules || echo "Regole SNMP incluse non aggiornate: l'API parte lo stesso." >&2
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 ${UVICORN_EXTRA_ARGS}
