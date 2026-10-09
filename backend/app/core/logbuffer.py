"""Ultime righe di log dell'API tenute in memoria, per il pacchetto diagnostico (scaricabile senza accesso al server)."""
import logging
import threading
from collections import deque

MAX_LINES = 3000
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class BufferHandler(logging.Handler):
    def __init__(self, capacity: int = MAX_LINES):
        super().__init__()
        self.lines: deque[str] = deque(maxlen=capacity)
        self.guard = threading.Lock()
        self.setFormatter(logging.Formatter(FORMAT))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
        except Exception:  # noqa: BLE001 - un messaggio scritto male non deve rompere il log
            self.handleError(record)
            return
        with self.guard:
            self.lines.append(line)

    def text(self) -> str:
        with self.guard:
            return "\n".join(self.lines)


buffer = BufferHandler()


def attach(*names: str) -> None:
    """Collega il buffer ai logger indicati (una volta sola anche se il modulo viene ricaricato)."""
    for name in names:
        logger = logging.getLogger(name)
        if buffer not in logger.handlers:
            logger.addHandler(buffer)
