"""Fase 3: scansione SNMP.

- `targets`: intervalli da scansionare -> elenco di IP
- `snmp`: lettura dei device con pysnmp (asyncio) -> HostData, senza toccare il database
- `planner`: confronta HostData con il database -> modifiche proposte (Proposal)
- `apply`: applica una modifica approvata
- `runner`: esecuzione di un job, coda e pianificazione (usato dal worker)
"""
