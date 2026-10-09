"""Worker delle scansioni SNMP: gira nel container `worker`, stessa immagine dell'API.

La coda è la tabella discovery_runs: l'API inserisce una riga 'queued' ("Avvia ora" o pianificazione)
e il worker la prende entro pochi secondi. Le scansioni non girano mai dentro una richiesta HTTP.
Un secondo thread copia i backup fuori dal server (services/offsite.py), così una scansione lunga non lo ferma.

Uso:  python -m app.worker
"""
import logging
import threading
import time

from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import settings
from app.database import SessionLocal
from app.discovery.runner import claim_next_run, execute_run, recover_interrupted, schedule_due_jobs
from app.services.offsite import offsite_loop

logger = logging.getLogger("netmap.worker")
SCHEDULE_EVERY = 60  # secondi tra un controllo e l'altro dei job pianificati


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pysnmp").setLevel(logging.WARNING)
    logger.info("Worker scansioni avviato")
    threading.Thread(target=offsite_loop, args=(SessionLocal,), name="offsite", daemon=True).start()
    recovered = False
    next_schedule = 0.0

    while True:
        try:
            with SessionLocal() as db:
                if not recovered:
                    if count := recover_interrupted(db):
                        logger.warning("%s scansioni interrotte segnate come fallite", count)
                    recovered = True
                if time.monotonic() >= next_schedule:
                    if count := schedule_due_jobs(db):
                        logger.info("%s job pianificati messi in coda", count)
                    next_schedule = time.monotonic() + SCHEDULE_EVERY
                run_id = claim_next_run(db)
            if run_id is not None:
                logger.info("Scansione %s avviata", run_id)
                with SessionLocal() as db:
                    run = execute_run(db, run_id)
                    logger.info("Scansione %s finita: %s", run_id, run.status)
                continue
        except (OperationalError, ProgrammingError) as exc:
            # Database non ancora pronto o migration non ancora applicata dall'API
            logger.warning("Database non pronto, riprovo tra 10 secondi (%s)", str(exc.orig).splitlines()[0])
            time.sleep(10)
            continue
        except Exception:
            logger.exception("Errore inatteso nel worker")
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
