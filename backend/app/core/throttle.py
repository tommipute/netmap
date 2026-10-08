"""Freno ai tentativi di accesso sbagliati e indirizzo vero del client dietro i reverse proxy.

I contatori stanno in memoria: l'API gira in un solo processo uvicorn (start.sh), e un riavvio li azzera.
"""
import math
import time
from dataclasses import dataclass

from fastapi import Request

from app.config import settings


@dataclass
class _Counter:
    failures: int = 0
    last: float = 0.0
    locked_until: float = 0.0


class Throttle:
    """Dopo `max_failures` errori ravvicinati blocca per `base_lock` secondi; ogni errore successivo raddoppia
    l'attesa fino a `max_lock`. Il conteggio riparte dopo `window` secondi senza errori o con success()."""

    def __init__(self, max_failures: int, base_lock: float, max_lock: float, window: float, clock=time.monotonic):
        self.max_failures, self.base_lock, self.max_lock, self.window = max_failures, base_lock, max_lock, window
        self.clock = clock
        self._counters: dict[str, _Counter] = {}

    def _current(self, key: str) -> _Counter | None:
        counter = self._counters.get(key)
        if counter and self.clock() - counter.last > max(self.window, counter.locked_until - counter.last):
            del self._counters[key]  # nessun errore da tempo e blocco finito
            return None
        return counter

    def retry_after(self, key: str) -> int:
        """Secondi da aspettare prima di poter riprovare (0 = libero)."""
        counter = self._current(key)
        return max(0, math.ceil(counter.locked_until - self.clock())) if counter else 0

    def failure(self, key: str) -> int:
        """Registra un errore; restituisce i secondi di blocco che ne seguono (0 = nessun blocco)."""
        now = self.clock()
        counter = self._current(key) or self._counters.setdefault(key, _Counter())
        counter.failures += 1
        counter.last = now
        if counter.failures < self.max_failures:
            return 0
        lock = min(self.base_lock * 2 ** (counter.failures - self.max_failures), self.max_lock)
        counter.locked_until = now + lock
        if len(self._counters) > 10_000:
            self._prune()
        return math.ceil(lock)

    def success(self, key: str) -> None:
        self._counters.pop(key, None)

    def clear(self) -> None:
        self._counters.clear()

    def _prune(self) -> None:
        for key in list(self._counters):
            self._current(key)


def client_ip(request: Request) -> str:
    """Indirizzo di chi fa la richiesta. Con TRUSTED_PROXIES = N (proxy fidati davanti all'API: nginx, Caddy) si
    legge da X-Forwarded-For contando N passaggi da destra, così un client non può inventarsi l'indirizzo."""
    peer = request.client.host if request.client else ""
    hops = settings.trusted_proxies
    if hops <= 0:
        return peer
    chain = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",") if part.strip()]
    chain.append(peer)
    return chain[-(hops + 1)] if len(chain) > hops else chain[0]
