"""File dati per snmpsim (formato .snmprec) a partire dalla descrizione di un device.

La descrizione è un dict (vedi app/lab/devices.py e tests/snmp_devices.py): sistema, interfacce, IP, ENTITY-MIB,
LLDP, CDP, tabelle MAC (BRIDGE / Q-BRIDGE), VLAN e ARP; per il monitor anche contatori, duplex e PoE. Serve ai test d'integrazione e alla rete di laboratorio.
"""
import ipaddress

INT, STR, HEX, OID, IPADDR, COUNTER, GAUGE, TICKS = "2", "4", "4x", "6", "64", "65", "66", "67"
COUNTER64 = "70"


def lldp_caps_hex(caps) -> str:
    """lldpRemSysCapEnabled: BITS in due byte, il primo bit è "other"."""
    from app.discovery.snmp import LLDP_CAPS
    return f"{sum(0x80 >> LLDP_CAPS.index(c) for c in caps):02x}00"


def mac_hex(mac: str) -> str:
    return mac.replace(":", "").lower()


def ip_arcs(address: str) -> str:
    return ".".join(str(b) for b in ipaddress.ip_address(address).packed)


def bitmap(positions, size: int | None = None) -> str:
    """Bitmap SNMP (PortList) in esadecimale: posizione 1 = bit più significativo del primo byte."""
    positions = list(positions)
    length = size or max(1, (max(positions, default=1) + 7) // 8)
    data = bytearray(length)
    for p in positions:
        data[(p - 1) // 8] |= 0x80 >> ((p - 1) % 8)
    return data.hex()


def snmprec(device: dict) -> str:
    rows: list[tuple[str, str, str]] = []
    add = lambda oid, kind, value: rows.append((oid, kind, str(value)))  # noqa: E731

    system = device["system"]
    add("1.3.6.1.2.1.1.1.0", STR, system["descr"])
    add("1.3.6.1.2.1.1.2.0", OID, system["object_id"])
    add("1.3.6.1.2.1.1.5.0", STR, system["name"])
    add("1.3.6.1.2.1.1.6.0", STR, system["location"])
    # Facoltativi: tipo di apparato (sysServices, capacità LLDP, Printer-MIB, UPS-MIB)
    if "services" in system:
        add("1.3.6.1.2.1.1.7.0", INT, system["services"])
    if "lldp_caps" in system:
        caps = ["other", "repeater", "bridge", "wlanAccessPoint", "router", "telephone", "docsis", "station"]
        add("1.0.8802.1.1.2.1.3.6.0", HEX, bitmap(caps.index(c) + 1 for c in system["lldp_caps"]))
    if system.get("printer"):
        add("1.3.6.1.2.1.43.5.1.1.1.1", INT, 3)
    if system.get("ups"):
        add("1.3.6.1.2.1.33.1.1.1.0", STR, "APC")

    for idx, (name, descr, if_type, mtu, mbps, mac, admin, oper, alias) in device["interfaces"].items():
        add(f"1.3.6.1.2.1.2.2.1.1.{idx}", INT, idx)
        add(f"1.3.6.1.2.1.2.2.1.2.{idx}", STR, descr)
        add(f"1.3.6.1.2.1.2.2.1.3.{idx}", INT, if_type)
        add(f"1.3.6.1.2.1.2.2.1.4.{idx}", INT, mtu)
        add(f"1.3.6.1.2.1.2.2.1.5.{idx}", GAUGE, min((mbps or 0) * 1_000_000, 4294967295))
        add(f"1.3.6.1.2.1.2.2.1.6.{idx}", HEX, mac_hex(mac))
        add(f"1.3.6.1.2.1.2.2.1.7.{idx}", INT, admin)
        add(f"1.3.6.1.2.1.2.2.1.8.{idx}", INT, oper)
        add(f"1.3.6.1.2.1.31.1.1.1.1.{idx}", STR, name)
        add(f"1.3.6.1.2.1.31.1.1.1.15.{idx}", GAUGE, mbps or 0)
        add(f"1.3.6.1.2.1.31.1.1.1.18.{idx}", STR, alias)

    # Facoltativi, per i dettagli delle porte del monitor
    if "uptime" in system:
        add("1.3.6.1.2.1.1.3.0", TICKS, system["uptime"])
    # ifIndex: (ifLastChange, errori in, errori out, scarti in, scarti out); un contatore come dict cresce nel tempo
    # (variazione "numeric" di snmpsim, es. {"initial": 1500, "rate": 0.01} = un errore ogni 100 secondi)
    for idx, (last_change, *counters) in device.get("port_counters", {}).items():
        add(f"1.3.6.1.2.1.2.2.1.9.{idx}", TICKS, last_change)
        for column, value in zip((14, 20, 13, 19), counters):
            if isinstance(value, dict):
                add(f"1.3.6.1.2.1.2.2.1.{column}.{idx}", f"{COUNTER}:numeric", ",".join(f"{k}={v}" for k, v in value.items()))
            else:
                add(f"1.3.6.1.2.1.2.2.1.{column}.{idx}", COUNTER, value)
    # Traffico: ifIndex -> (byte/s in, byte/s out). Contatori che salgono con un'onda di circa 3 ore e mezza
    # (±60% a ogni lettura da 5 minuti); con "traffic_32bit" solo ifIn/OutOctets a 32 bit, che fanno il giro
    hc = not device.get("traffic_32bit")
    for idx, rates in device.get("traffic", {}).items():
        for column, rate in zip((6, 10) if hc else (10, 16), rates):
            oid = f"1.3.6.1.2.1.31.1.1.1.{column}.{idx}" if hc else f"1.3.6.1.2.1.2.2.1.{column}.{idx}"
            add(oid, f"{COUNTER64 if hc else COUNTER}:numeric", _wave(rate, wrap=not hc))
    for idx, duplex in device.get("duplex", {}).items():  # 2 = half, 3 = full
        add(f"1.3.6.1.2.1.10.7.2.1.19.{idx}", INT, duplex)
    poe = device.get("poe")
    if poe:
        for group, (budget_w, used_w) in poe["groups"].items():
            add(f"1.3.6.1.2.1.105.1.3.1.1.2.{group}", GAUGE, budget_w)
            add(f"1.3.6.1.2.1.105.1.3.1.1.3.{group}", INT, 1)
            add(f"1.3.6.1.2.1.105.1.3.1.1.4.{group}", GAUGE, used_w)
        # (gruppo, porta): (rilevamento: 2 cerca, 3 alimenta, 4 guasto; classe 0-4 o None; mW; ifIndex per Cisco)
        for (group, port), (detection, power_class, mw, if_index) in poe["ports"].items():
            index = f"{group}.{port}"
            add(f"1.3.6.1.2.1.105.1.1.1.6.{index}", INT, detection)
            add(f"1.3.6.1.2.1.105.1.1.1.10.{index}", INT, 1 if power_class is None else power_class + 1)
            if poe["vendor"] == "cisco":  # CISCO-POWER-ETHERNET-EXT-MIB e la porta via ENTITY-MIB
                entity = 5000 + group * 100 + port
                add(f"1.3.6.1.4.1.9.9.402.1.2.1.9.{index}", GAUGE, mw)
                add(f"1.3.6.1.4.1.9.9.402.1.2.1.11.{index}", INT, entity)
                add(f"1.3.6.1.2.1.47.1.3.2.1.2.{entity}.0", OID, f"1.3.6.1.2.1.2.2.1.1.{if_index}")
            elif poe["vendor"] == "hp":  # HP-ICF-POE-MIB, stesso indice
                add(f"1.3.6.1.4.1.11.2.14.11.1.9.1.1.1.3.{index}", INT, mw)

    # STP: {"changes": contatore (anche dict "numeric"), "since": centesimi dall'ultimo cambio, "ports": {porta bridge: stato}}
    stp = device.get("stp")
    if stp:
        changes = stp["changes"]
        if isinstance(changes, dict):
            add("1.3.6.1.2.1.17.2.4.0", f"{COUNTER}:numeric", ",".join(f"{k}={v}" for k, v in changes.items()))
        else:
            add("1.3.6.1.2.1.17.2.4.0", COUNTER, changes)
        add("1.3.6.1.2.1.17.2.3.0", TICKS, stp["since"])
        for base_port, state in stp.get("ports", {}).items():  # 2 blocking, 5 forwarding
            add(f"1.3.6.1.2.1.17.2.15.1.3.{base_port}", INT, state)
    # Cisco err-disable: {ifIndex: causa} (2 = bpduGuard, 9 = portSecurityViolation…), VLAN 0 = tutta la porta
    for idx, cause in device.get("err_disabled", {}).items():
        add(f"1.3.6.1.4.1.9.9.548.1.3.1.1.2.{idx}.0", INT, cause)

    for address, if_index, mask in device["ipv4"]:
        add(f"1.3.6.1.2.1.4.20.1.1.{address}", IPADDR, address)
        add(f"1.3.6.1.2.1.4.20.1.2.{address}", INT, if_index)
        add(f"1.3.6.1.2.1.4.20.1.3.{address}", IPADDR, mask)
    for address, if_index, prefixlen in device["ipv6"]:
        index = f"2.16.{ip_arcs(address)}"
        add(f"1.3.6.1.2.1.4.34.1.3.{index}", INT, if_index)
        add(f"1.3.6.1.2.1.4.34.1.5.{index}", OID, f"1.3.6.1.2.1.4.32.1.5.{if_index}.2.16.{ip_arcs(address)}.{prefixlen}")

    for idx, (klass, serial, model, *relpos) in device["entities"].items():
        if relpos:  # membro di uno stack
            add(f"1.3.6.1.2.1.47.1.1.1.1.6.{idx}", INT, relpos[0])
        add(f"1.3.6.1.2.1.47.1.1.1.1.5.{idx}", INT, klass)
        add(f"1.3.6.1.2.1.47.1.1.1.1.11.{idx}", STR, serial)
        add(f"1.3.6.1.2.1.47.1.1.1.1.13.{idx}", STR, model)

    for port_num, (subtype, port_id, descr) in device["lldp_local"].items():
        add(f"1.0.8802.1.1.2.1.3.7.1.2.{port_num}", INT, subtype)
        add(f"1.0.8802.1.1.2.1.3.7.1.3.{port_num}", STR, port_id)
        add(f"1.0.8802.1.1.2.1.3.7.1.4.{port_num}", STR, descr)

    # In fondo, facoltative: le capacità del vicino (bridge, router…) e, per CDP, il numero di cdpCacheCapabilities
    for (port_num, rem_index), (c_type, chassis, p_type, port, p_descr, sys_name, mgmt, *caps) in device["lldp_remote"].items():
        index = f"0.{port_num}.{rem_index}"
        if caps:
            add(f"1.0.8802.1.1.2.1.4.1.1.12.{index}", HEX, lldp_caps_hex(caps[0]))
        add(f"1.0.8802.1.1.2.1.4.1.1.4.{index}", INT, c_type)
        add(f"1.0.8802.1.1.2.1.4.1.1.5.{index}", HEX, mac_hex(chassis))
        add(f"1.0.8802.1.1.2.1.4.1.1.6.{index}", INT, p_type)
        add(f"1.0.8802.1.1.2.1.4.1.1.7.{index}", STR, port)
        add(f"1.0.8802.1.1.2.1.4.1.1.8.{index}", STR, p_descr)
        add(f"1.0.8802.1.1.2.1.4.1.1.9.{index}", STR, sys_name)
        if mgmt:
            add(f"1.0.8802.1.1.2.1.4.2.1.3.{index}.1.4.{mgmt}", INT, 2)

    for (if_index, cdp_index), (device_id, port, address, *caps) in device["cdp"].items():
        index = f"{if_index}.{cdp_index}"
        if caps:
            add(f"1.3.6.1.4.1.9.9.23.1.2.1.1.9.{index}", HEX, f"{caps[0]:08x}")
        add(f"1.3.6.1.4.1.9.9.23.1.2.1.1.3.{index}", INT, 1)
        add(f"1.3.6.1.4.1.9.9.23.1.2.1.1.4.{index}", HEX, ipaddress.ip_address(address).packed.hex())
        add(f"1.3.6.1.4.1.9.9.23.1.2.1.1.6.{index}", STR, device_id)
        add(f"1.3.6.1.4.1.9.9.23.1.2.1.1.7.{index}", STR, port)

    for base_port, if_index in device["bridge_ports"].items():
        add(f"1.3.6.1.2.1.17.1.4.1.2.{base_port}", INT, if_index)
    for base_port, vid in device["pvid"].items():
        add(f"1.3.6.1.2.1.17.7.1.4.5.1.1.{base_port}", GAUGE, vid)
    for vlan, mac, base_port, status in device["fdb"]:
        arcs = ".".join(str(b) for b in bytes.fromhex(mac_hex(mac)))
        if device["qbridge"]:
            add(f"1.3.6.1.2.1.17.7.1.2.2.1.2.{vlan}.{arcs}", INT, base_port)
            add(f"1.3.6.1.2.1.17.7.1.2.2.1.3.{vlan}.{arcs}", INT, status)
        else:
            add(f"1.3.6.1.2.1.17.4.3.1.2.{arcs}", INT, base_port)
            add(f"1.3.6.1.2.1.17.4.3.1.3.{arcs}", INT, status)
    for vid, name in device["vlans"].items():
        add(f"1.3.6.1.2.1.17.7.1.4.3.1.1.{vid}", STR, name)
    # Q-BRIDGE: porte bridge in cui esce ogni VLAN e dove esce senza tag
    for vid, (egress, untagged) in device.get("vlan_ports", {}).items():
        add(f"1.3.6.1.2.1.17.7.1.4.3.1.2.{vid}", HEX, bitmap(egress))
        add(f"1.3.6.1.2.1.17.7.1.4.3.1.4.{vid}", HEX, bitmap(untagged))
    # Cisco: nomi VTP, VLAN delle porte access, trunk con VLAN nativa e VLAN permesse
    cisco = device.get("cisco", {})
    for vid, name in cisco.get("names", {}).items():
        add(f"1.3.6.1.4.1.9.9.46.1.3.1.1.4.1.{vid}", STR, name)
    for if_index, vid in cisco.get("access", {}).items():
        add(f"1.3.6.1.4.1.9.9.68.1.2.2.1.2.{if_index}", INT, vid)
    for if_index, (native, allowed) in cisco.get("trunks", {}).items():
        add(f"1.3.6.1.4.1.9.9.46.1.6.1.1.4.{if_index}", HEX, bitmap([v + 1 for v in allowed], size=128))
        add(f"1.3.6.1.4.1.9.9.46.1.6.1.1.5.{if_index}", INT, native)
        add(f"1.3.6.1.4.1.9.9.46.1.6.1.1.14.{if_index}", INT, 1)
    for if_index, address, mac in device["arp"]:
        add(f"1.3.6.1.2.1.4.22.1.2.{if_index}.{address}", HEX, mac_hex(mac))
        add(f"1.3.6.1.2.1.4.22.1.4.{if_index}.{address}", INT, 3)

    return _render(rows)


def _render(rows: list[tuple[str, str, str]]) -> str:
    rows.sort(key=lambda row: tuple(int(part) for part in row[0].split(".")))
    return "".join(f"{oid}|{kind}|{value}\n" for oid, kind, value in rows)


def snmprec_vlan(device: dict, vid: int) -> str:
    """Cisco: quello che lo switch risponde con `community@VLAN` (SNMPv3: context `vlan-N`), cioè la BRIDGE-MIB di
    quella VLAN. Le righe stanno in device["cisco"]["fdb"][vid]: (MAC, porta bridge, stato)."""
    rows: list[tuple[str, str, str]] = []
    for base_port, if_index in device["bridge_ports"].items():
        rows.append((f"1.3.6.1.2.1.17.1.4.1.2.{base_port}", INT, str(if_index)))
    for mac, base_port, status in device.get("cisco", {}).get("fdb", {}).get(vid, []):
        arcs = ".".join(str(b) for b in bytes.fromhex(mac_hex(mac)))
        rows.append((f"1.3.6.1.2.1.17.4.3.1.2.{arcs}", INT, str(base_port)))
        rows.append((f"1.3.6.1.2.1.17.4.3.1.3.{arcs}", INT, str(status)))
    return _render(rows)


def snmprec_files(device: dict, community: str) -> dict[str, str]:
    """I file dati di un apparato, per nome: `<community>.snmprec` e, sui Cisco, uno per VLAN (`<community>@N` per
    SNMP v1/v2c, `vlan-N` per i context SNMPv3). snmpsim sceglie il file dalla community o dal context."""
    files = {f"{community}.snmprec": snmprec(device)}
    for vid in device.get("cisco", {}).get("names", {}):
        if vid != 1 and vid not in range(1002, 1006):
            data = snmprec_vlan(device, vid)
            files[f"{community}@{vid}.snmprec"] = data
            files[f"vlan-{vid}.snmprec"] = data
    return files


def _wave(rate: float, wrap: bool) -> str:
    """Variazione "numeric" di snmpsim per un contatore di byte: a ogni lettura sale di rate × secondi passati
    (offset) più un'onda (sin del tempo × scale), così il grafico sale e scende."""
    speed = 0.0005  # radianti al secondo: un giro ogni 3,5 ore circa
    settings = {"cumulative": 1, "function": "sin", "rate": speed, "scale": round(rate * 300 * 0.6),
                "offset": round(rate / speed), "initial": round(rate * 1000)}
    if wrap:
        settings["wrap"] = 1
    return ",".join(f"{k}={v}" for k, v in settings.items())
