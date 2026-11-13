"""Resoconto di una lettura SNMP per la scheda "Cosa ho letto" del device e per la prova degli indirizzi.

Dice cosa ha risposto l'apparato tabella per tabella, da dove vengono modello e tabella MAC, quali stranezze dello
switch NetMap ha aggirato e cosa ha dovuto scartare: serve a capire da soli perché manca qualcosa. Le note sono
codici con un numero (righe interessate), il testo lo mette l'interfaccia.
"""
from app.discovery.snmp import HostData
from app.discovery.vendors import vendor_name


def build_report(hd: HostData, renamed_ports: int = 0) -> dict:
    notes = dict(hd.notes)
    if unmatched := sum(1 for n in hd.neighbors if n.local_if_index is None):
        notes["neighbor_no_local_port"] = unmatched
    if renamed_ports:
        notes["renamed_ports"] = renamed_ports
    return {
        "host": hd.host,
        "profile": hd.profile_name,
        "sys_name": hd.sys_name,
        "sys_object_id": hd.sys_object_id,
        "manufacturer": vendor_name(hd.sys_object_id) if hd.sys_object_id else None,
        "sys_descr": hd.sys_descr,
        "model": hd.model,
        "model_source": hd.model_source,
        "serial": hd.serial,
        "counts": {
            "interfaces": len(hd.interfaces),
            "ips": len(hd.ips),
            "members": len(hd.members),
            "lldp": sum(1 for n in hd.neighbors if n.protocol == "lldp"),
            "cdp": sum(1 for n in hd.neighbors if n.protocol == "cdp"),
            "vlans": len(hd.vlans),
            "port_vlans": len(hd.port_vlans),
            "fdb": len(hd.fdb),
            "arp": len(hd.arp),
        },
        "fdb_source": hd.fdb_source,
        "notes": {key: value for key, value in sorted(notes.items()) if value},
        "problems": list(hd.problems),
    }
