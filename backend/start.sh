#!/bin/sh
set -e

# Primo avvio: se non c'è ancora nessuna migration, la genera dai modelli
if ! ls alembic/versions/*.py >/dev/null 2>&1; then
  echo "Nessuna migration trovata: genero quella iniziale dai modelli..."
  alembic revision --autogenerate -m "iniziale"
fi

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 ${UVICORN_EXTRA_ARGS}
