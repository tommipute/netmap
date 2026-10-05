"""Monitor dello stato live: gira nel container `monitor`, stessa immagine dell'API.

Ogni MONITOR_INTERVAL_SECONDS controlla con ping (e SNMP, se il device ha un profilo) tutti i device attivi
che hanno un IP di management, e aggiorna raggiungibilità e stato delle porte.

Uso:  python -m app.monitor
"""
import logging
import time

from sqlalchemy.exc import OperationalError, ProgrammingError

from app.config import settings
from app.database import SessionLocal
from app.services.monitor import check_devices

logger = logging.getLogger("netmap.monitor")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("pysnmp").setLevel(logging.WARNING)
    if settings.monitor_interval_seconds <= 0:
        logger.info("Monitor disattivato (MONITOR_INTERVAL_SECONDS=0)")
        while True:
            time.sleep(3600)
    logger.info("Monitor avviato: un controllo ogni %s secondi", settings.monitor_interval_seconds)
    while True:
        started = time.monotonic()
        try:
            with SessionLocal() as db:
                result = check_devices(db)
            logger.info("Controllati %s device: %s raggiungibili, %s no", result["checked"], result["up"], result["down"])
        except (OperationalError, ProgrammingError) as exc:
            logger.warning("Database non pronto, riprovo tra 10 secondi (%s)", str(exc.orig).splitlines()[0])
            time.sleep(10)
            continue
        except Exception:
            logger.exception("Errore inatteso nel monitor")
        time.sleep(max(5.0, settings.monitor_interval_seconds - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
