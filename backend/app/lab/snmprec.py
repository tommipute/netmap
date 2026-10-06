"""File dati per snmpsim (formato .snmprec) a partire dalla descrizione di un device.

La descrizione è un dict (vedi app/lab/devices.py e tests/snmp_devices.py): sistema, interfacce, IP, ENTITY-MIB,
LLDP, CDP, tabelle MAC (BRIDGE / Q-BRIDGE), VLAN e ARP. Serve ai test d'integrazione e alla rete di laboratorio.
"""
import ipaddress

INT, STR, HEX, OID, IPADDR, GAUGE = "2", "4", "4x", "6", "64", "66"


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

    for address, if_index, mask in device["ipv4"]:
        add(f"1.3.6.1.2.1.4.20.1.1.{address}", IPADDR, address)
        add(f"1.3.6.1.2.1.4.20.1.2.{address}", INT, if_index)
        add(f"1.3.6.1.2.1.4.20.1.3.{address}", IPADDR, mask)
    for address, if_index, prefixlen in device["ipv6"]:
        index = f"2.16.{ip_arcs(address)}"
        add(f"1.3.6.1.2.1.4.34.1.3.{index}", INT, if_index)
        add(f"1.3.6.1.2.1.4.34.1.5.{index}", OID, f"1.3.6.1.2.1.4.32.1.5.{if_index}.2.16.{ip_arcs(address)}.{prefixlen}")

    for idx, (klass, serial, model) in device["entities"].items():
        add(f"1.3.6.1.2.1.47.1.1.1.1.5.{idx}", INT, klass)
        add(f"1.3.6.1.2.1.47.1.1.1.1.11.{idx}", STR, serial)
        add(f"1.3.6.1.2.1.47.1.1.1.1.13.{idx}", STR, model)

    for port_num, (subtype, port_id, descr) in device["lldp_local"].items():
        add(f"1.0.8802.1.1.2.1.3.7.1.2.{port_num}", INT, subtype)
        add(f"1.0.8802.1.1.2.1.3.7.1.3.{port_num}", STR, port_id)
        add(f"1.0.8802.1.1.2.1.3.7.1.4.{port_num}", STR, descr)

    for (port_num, rem_index), (c_type, chassis, p_type, port, p_descr, sys_name, mgmt) in device["lldp_remote"].items():
        index = f"0.{port_num}.{rem_index}"
        add(f"1.0.8802.1.1.2.1.4.1.1.4.{index}", INT, c_type)
        add(f"1.0.8802.1.1.2.1.4.1.1.5.{index}", HEX, mac_hex(chassis))
        add(f"1.0.8802.1.1.2.1.4.1.1.6.{index}", INT, p_type)
        add(f"1.0.8802.1.1.2.1.4.1.1.7.{index}", STR, port)
        add(f"1.0.8802.1.1.2.1.4.1.1.8.{index}", STR, p_descr)
        add(f"1.0.8802.1.1.2.1.4.1.1.9.{index}", STR, sys_name)
        if mgmt:
            add(f"1.0.8802.1.1.2.1.4.2.1.3.{index}.1.4.{mgmt}", INT, 2)

    for (if_index, cdp_index), (device_id, port, address) in device["cdp"].items():
        index = f"{if_index}.{cdp_index}"
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

    rows.sort(key=lambda row: tuple(int(part) for part in row[0].split(".")))
    return "".join(f"{oid}|{kind}|{value}\n" for oid, kind, value in rows)
