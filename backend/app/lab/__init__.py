"""Rete di laboratorio per provare scansione SNMP, "dov'è collegato?" e stato live senza apparati veri.

Avvio: `docker compose --profile lab up -d` (un container per apparato, rete 172.31.250.0/24).
Preparazione di NetMap: `docker compose exec api python -m app.lab prepara`.
"""
