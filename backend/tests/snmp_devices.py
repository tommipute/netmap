"""Due switch finti per i test della scansione: sw-sim-01 (Cisco) e sw-sim-02 (HPE), collegati via LLDP.

`snmprec(device)` produce il file dati per snmpsim; gli stessi valori servono ai test del collector.
"""
import ipaddress

from app.lab.snmprec import snmprec  # noqa: F401  (usato dai test d'integrazione)

SW1_CHASSIS_MAC = "00:11:22:33:44:00"
SW2_CHASSIS_MAC = "00:22:33:44:55:00"
PC_A_MAC = "00:50:56:00:00:10"
PC_B_MAC = "00:50:56:00:00:20"


SW1 = {
    "system": {
        "descr": "Cisco IOS Software, Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4",
        "object_id": "1.3.6.1.4.1.9.1.2494",
        "name": "sw-sim-01.lab.local",
        "location": "Laboratorio",
    },
    # ifIndex: (ifName, ifDescr, ifType, MTU, Mbps, MAC, admin, oper, alias)
    "interfaces": {
        1: ("Gi1/0/1", "GigabitEthernet1/0/1", 6, 1500, 1000, "00:11:22:33:44:01", 1, 1, "Uplink firewall"),
        2: ("Gi1/0/2", "GigabitEthernet1/0/2", 6, 1500, 1000, "00:11:22:33:44:02", 2, 2, ""),
        9: ("Te1/1/1", "TenGigabitEthernet1/1/1", 6, 1500, 10000, "00:11:22:33:44:09", 1, 1, "verso sw-sim-02"),
        99: ("Vl99", "Vlan99", 136, 1500, 1000, "00:11:22:33:44:63", 1, 1, ""),
        200: ("Po1", "Port-channel1", 161, 1500, 2000, "00:11:22:33:44:c8", 1, 7, ""),
    },
    "ipv4": [("10.99.0.1", 99, "255.255.255.0"), ("127.0.0.1", 99, "255.0.0.0")],
    "ipv6": [("fd00::1", 99, 64)],
    "entities": {1000: (3, "FOCSIM0001", "C9300-48P"), 1001: (9, "MODSIM01", "C9300-NM-8X")},
    # lldpLocPortNum: (subtype, id, descr)
    "lldp_local": {9: (5, "Te1/1/1", "TenGigabitEthernet1/1/1")},
    # (porta locale, indice): (subtype chassis, chassis id, subtype porta, porta, descr porta, sysName, IP mgmt)
    "lldp_remote": {(9, 1): (4, SW2_CHASSIS_MAC, 5, "49", "49", "sw-sim-02", "10.99.0.2")},
    # (ifIndex locale, indice): (device id, porta, IP)
    "cdp": {(1, 5): ("phone-01(SEP001122AABB)", "Port 1", "10.99.0.50")},
    # Tabella MAC: porta bridge -> ifIndex, PVID per porta bridge, righe (VLAN o None, MAC, porta bridge, stato)
    # Cisco senza Q-BRIDGE: solo BRIDGE-MIB, senza VLAN
    "qbridge": False,
    "bridge_ports": {1: 1, 2: 2, 9: 9},
    "pvid": {},
    "fdb": [
        (None, PC_A_MAC, 1, 3),               # PC-A collegato a Gi1/0/1
        (None, PC_B_MAC, 9, 3),               # PC-B visto dall'uplink verso sw-sim-02
        (None, "00:22:33:44:55:02", 9, 3),
        (None, "00:11:22:33:44:01", 1, 4),    # MAC dello switch stesso (self): da ignorare
    ],
    "vlans": {},
    # ARP: (ifIndex, IP, MAC)
    "arp": [(99, "10.99.0.10", PC_A_MAC), (99, "10.99.0.20", PC_B_MAC)],
}

SW2 = {
    "system": {
        "descr": "HP J9728A 2920-48G Switch, revision WB.16.10",
        "object_id": "1.3.6.1.4.1.11.2.3.7.11.181",
        "name": "sw-sim-02",
        "location": "Laboratorio",
    },
    "interfaces": {
        1: ("1", "1", 6, 1500, 1000, "00:22:33:44:55:01", 1, 1, ""),
        2: ("2", "2", 6, 1500, 1000, "00:22:33:44:55:02", 1, 2, ""),
        49: ("49", "49", 6, 1500, 10000, "00:22:33:44:55:31", 1, 1, "uplink core"),
        1099: ("VLAN99", "VLAN99", 53, 1500, None, SW2_CHASSIS_MAC, 1, 1, ""),
    },
    "ipv4": [("10.99.0.2", 1099, "255.255.255.0")],
    "ipv6": [],
    "entities": {1: (3, "SGSIM0002", "J9728A")},
    # numerazione LLDP diversa dagli ifIndex: si abbina per nome
    "lldp_local": {101: (7, "49", "49")},
    "lldp_remote": {(101, 3): (4, SW1_CHASSIS_MAC, 5, "TenGigabitEthernet1/1/1", "", "sw-sim-01.lab.local", None)},
    "cdp": {},
    "qbridge": True,
    "bridge_ports": {1: 1, 2: 2, 49: 49},
    "pvid": {1: 99, 2: 99, 49: 1},
    "fdb": [
        (99, PC_B_MAC, 1, 3),                 # PC-B collegato alla porta 1
        (99, PC_A_MAC, 49, 3),                # PC-A visto dall'uplink verso sw-sim-01
        (99, "00:11:22:33:44:63", 49, 3),
    ],
    "vlans": {1: "DEFAULT_VLAN", 99: "LAB"},
    "arp": [],
}


def host_data(device: dict, host: str, profile_id: int | None = None, profile_name: str | None = None):
    """Quello che il collector deve restituire leggendo `device` (serve anche come scansione finta)."""
    from app.discovery.snmp import OPER_STATUS, ArpEntry, FdbEntry, HostData, IfData, IpData, NeighborData

    interfaces = [
        IfData(
            if_index=idx, name=name, descr=descr, alias=alias or None, if_type=if_type, mtu=mtu,
            speed_mbps=mbps or None, mac=mac.upper(), admin_up={1: True, 2: False}.get(admin),
            oper_status=OPER_STATUS.get(oper),
        )
        for idx, (name, descr, if_type, mtu, mbps, mac, admin, oper, alias) in sorted(device["interfaces"].items())
    ]
    by_name = {}
    for i in interfaces:
        by_name.setdefault(i.name, i.if_index)
        by_name.setdefault(i.descr, i.if_index)
    local_ports = {num: by_name.get(port_id, num) for num, (_s, port_id, _d) in device["lldp_local"].items()}

    ips = [
        IpData(address=f"{a}/{ipaddress.IPv4Network(f'0.0.0.0/{mask}').prefixlen}", if_index=idx)
        for a, idx, mask in sorted(device["ipv4"], key=lambda r: ipaddress.ip_address(r[0]))
        if not a.startswith("127.")
    ] + [IpData(address=f"{a}/{plen}", if_index=idx) for a, idx, plen in device["ipv6"]]

    chassis = sorted((i, s, m) for i, (klass, s, m) in device["entities"].items() if klass == 3)
    neighbors = [
        NeighborData(
            protocol="lldp", local_if_index=local_ports.get(port_num), sys_name=sys_name, chassis_mac=chassis_id.upper(),
            port_id=port, port_id_type="local" if p_type == 7 else "name", port_descr=p_descr or None,
            addresses=[mgmt] if mgmt else [],
        )
        for (port_num, _i), (_c, chassis_id, p_type, port, p_descr, sys_name, mgmt) in sorted(device["lldp_remote"].items())
    ] + [
        NeighborData(protocol="cdp", local_if_index=if_index, sys_name=dev_id.split("(")[0], port_id=port, addresses=[addr])
        for (if_index, _i), (dev_id, port, addr) in sorted(device["cdp"].items())
    ]
    bridge, pvid = device["bridge_ports"], device["pvid"]
    port_vlans = {bridge[bp]: vid for bp, vid in pvid.items()}
    fdb = sorted(
        {
            (mac.upper(), bridge[bp], vlan if device["qbridge"] else port_vlans.get(bridge[bp]))
            for vlan, mac, bp, status in device["fdb"] if status == 3
        },
        key=lambda e: (e[0], e[1], e[2] or 0),
    )
    arp = [ArpEntry(ip=ip, mac=mac.upper(), if_index=idx)
           for idx, ip, mac in sorted(device["arp"], key=lambda r: ipaddress.ip_address(r[1]))]
    system = device["system"]
    return HostData(
        host=host, profile_id=profile_id, profile_name=profile_name,
        sys_name=system["name"], sys_descr=system["descr"], sys_object_id=system["object_id"],
        sys_location=system["location"], serial=chassis[0][1] if chassis else None,
        model=chassis[0][2] if chassis else None, interfaces=interfaces, ips=ips, neighbors=neighbors,
        fdb=[FdbEntry(mac=m, if_index=i, vlan=v) for m, i, v in fdb], arp=arp,
        vlans=dict(device["vlans"]), port_vlans=port_vlans,
    )
