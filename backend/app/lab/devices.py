"""Rete di laboratorio: cinque apparati finti che rispondono a SNMP e al ping (container "lab-*").

    fw-lab-01 (FortiGate) ── core-lab-01 (Catalyst 9300) ─┬─ sw-lab-p1 (HPE 2930F, LLDP)
                                                          ├─ sw-lab-p2 (HPE 2930F, LLDP)
                                                          └─ sw-lab-p3 (Catalyst 1000, CDP)

Sugli switch di piano ci sono PC, una stampante, un telefono IP con un PC dietro e un access point con
dei client Wi-Fi; il core ha la tabella ARP delle VLAN 10 (uffici) e 20 (voce). Il formato dei dict è quello
di app/lab/snmprec.py.
"""
LAB_SUBNET = "172.31.250.0/24"
LAB_TARGETS = "172.31.250.10-30"  # .1 è il gateway di Docker (il computer che ospita i container)
COMMUNITY = "public"

FW_IP, CORE_IP, P1_IP, P2_IP, P3_IP = "172.31.250.10", "172.31.250.11", "172.31.250.21", "172.31.250.22", "172.31.250.23"
MASK = "255.255.255.0"

# MAC di chassis (OUI dei produttori veri) e degli endpoint
FW_MAC, CORE_MAC = "00:09:0f:aa:00:00", "70:0f:6a:aa:00:00"
P1_MAC, P2_MAC, P3_MAC = "94:18:82:aa:01:00", "94:18:82:aa:02:00", "00:5d:73:aa:03:00"
SERVER = ("00:50:56:c0:00:01", "10.10.10.10")
PC1, PC2, PC3, PC4, PC5 = (
    ("00:50:56:a1:00:01", "10.10.10.101"),
    ("00:50:56:a1:00:02", "10.10.10.102"),
    ("00:50:56:a1:00:03", "10.10.10.103"),
    ("00:50:56:a1:00:04", "10.10.10.104"),
    ("00:50:56:a1:00:05", "10.10.10.105"),
)
PRINTER = ("00:1b:a9:00:00:01", "10.10.10.50")
PHONE = ("00:04:f2:00:00:01", "10.10.20.11")
AP = ("00:3a:7d:00:00:01", "10.10.10.60")
WIFI = [(f"00:50:56:b2:00:0{i}", f"10.10.10.15{i}") for i in range(1, 4)]

LEARNED, SELF = 3, 4
VLANS = {1: "DEFAULT_VLAN", 10: "UFFICI", 20: "VOCE", 99: "MGMT"}
# Cisco: nomi VTP (le 1002-1005 ci sono sempre e NetMap deve ignorarle), trunk con nativa 1 che permette tutto
CISCO_VLANS = {1: "default", 10: "UFFICI", 20: "VOCE", 99: "MGMT",
               1002: "fddi-default", 1003: "token-ring-default", 1004: "fddinet-default", 1005: "trnet-default"}
TRUNK = (1, list(range(1, 1024)))


def _port_mac(chassis: str, index: int) -> str:
    """MAC di una porta: quello dello chassis con l'ultimo byte = indice (ogni apparato ha il suo prefisso)."""
    return f"{chassis[:-2]}{index & 0xFF:02x}"


def _iface(chassis, index, name, descr=None, if_type=6, mbps=1000, up=True, alias=""):
    """(ifName, ifDescr, ifType, MTU, Mbps, MAC, admin, oper, alias) come in snmprec.py"""
    return (name, descr or name, if_type, 1500, mbps, _port_mac(chassis, index), 1, 1 if up else 2, alias)


def _system(name, descr, object_id):
    return {"descr": descr, "object_id": object_id, "name": name, "location": "Laboratorio NetMap"}


FW = {
    "system": _system("fw-lab-01", "FortiGate-100F v7.2.8,build1639,240313 (GA.M)", "1.3.6.1.4.1.12356.101.1.1004"),
    "interfaces": {
        1: _iface(FW_MAC, 1, "port1", alias="LAN verso core"),
        2: _iface(FW_MAC, 2, "wan1", alias="Internet"),
        3: _iface(FW_MAC, 3, "mgmt", alias="Management"),
    },
    "ipv4": [(FW_IP, 3, MASK), ("10.10.10.254", 1, MASK)],
    "ipv6": [],
    "entities": {1: (3, "FG100FTK22000001", "FortiGate-100F")},
    "lldp_local": {1: (5, "port1", "port1")},
    "lldp_remote": {(1, 1): (4, CORE_MAC, 5, "Gi1/0/1", "GigabitEthernet1/0/1", "core-lab-01", CORE_IP)},
    "cdp": {},
    "qbridge": False,
    "bridge_ports": {},
    "pvid": {},
    "fdb": [],
    "vlans": {},
    "arp": [],
}

CORE = {
    "system": _system(
        "core-lab-01.lab.local",
        "Cisco IOS Software [Cupertino], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 17.9.4",
        "1.3.6.1.4.1.9.1.2494",
    ),
    "interfaces": {
        1: _iface(CORE_MAC, 1, "Gi1/0/1", "GigabitEthernet1/0/1", alias="Firewall"),
        2: _iface(CORE_MAC, 2, "Gi1/0/2", "GigabitEthernet1/0/2", alias="Server file"),
        3: _iface(CORE_MAC, 3, "Gi1/0/3", "GigabitEthernet1/0/3", up=False),
        9: _iface(CORE_MAC, 9, "Te1/1/1", "TenGigabitEthernet1/1/1", mbps=10000, alias="Piano 1"),
        10: _iface(CORE_MAC, 10, "Te1/1/2", "TenGigabitEthernet1/1/2", mbps=10000, alias="Piano 2"),
        11: _iface(CORE_MAC, 11, "Te1/1/3", "TenGigabitEthernet1/1/3", mbps=10000, alias="Piano 3"),
        110: _iface(CORE_MAC, 110, "Vl10", "Vlan10", if_type=136),
        120: _iface(CORE_MAC, 120, "Vl20", "Vlan20", if_type=136),
        199: _iface(CORE_MAC, 199, "Vl99", "Vlan99", if_type=136),
    },
    "ipv4": [(CORE_IP, 199, MASK), ("10.10.10.1", 110, MASK), ("10.10.20.1", 120, MASK)],
    "ipv6": [],
    "entities": {1000: (3, "FOC2611LAB1", "C9300-48P"), 1001: (9, "FOC2611LAB2", "C9300-NM-8X")},
    "lldp_local": {
        1: (5, "Gi1/0/1", "GigabitEthernet1/0/1"),
        9: (5, "Te1/1/1", "TenGigabitEthernet1/1/1"),
        10: (5, "Te1/1/2", "TenGigabitEthernet1/1/2"),
    },
    "lldp_remote": {
        (1, 1): (4, FW_MAC, 5, "port1", "port1", "fw-lab-01", FW_IP),
        (9, 2): (4, P1_MAC, 5, "49", "49", "sw-lab-p1", P1_IP),
        (10, 3): (4, P2_MAC, 5, "49", "49", "sw-lab-p2", P2_IP),
    },
    # Lo switch Cisco del piano 3 si vede solo via CDP
    "cdp": {(11, 1): ("sw-lab-p3", "GigabitEthernet1/0/25", P3_IP)},
    "cisco": {"names": CISCO_VLANS, "access": {1: 10, 2: 10}, "trunks": {9: TRUNK, 10: TRUNK, 11: TRUNK}},
    "qbridge": False,
    "bridge_ports": {1: 1, 2: 2, 9: 9, 10: 10, 11: 11},
    "pvid": {},
    "fdb": [
        (None, _port_mac(FW_MAC, 1), 1, LEARNED),
        (None, SERVER[0], 2, LEARNED),
        *[(None, mac, 9, LEARNED) for mac, _ in (PC1, PC2, PRINTER)],
        *[(None, mac, 10, LEARNED) for mac, _ in (PHONE, PC3, PC4)],
        *[(None, mac, 11, LEARNED) for mac, _ in (PC5, AP, *WIFI)],
        (None, _port_mac(CORE_MAC, 1), 1, SELF),
    ],
    "vlans": {},
    "arp": [
        *[(110, ip, mac) for mac, ip in (SERVER, PC1, PC2, PC3, PC4, PC5, PRINTER, AP, *WIFI)],
        (120, PHONE[1], PHONE[0]),
    ],
}


def _hpe(name, ip, chassis, serial, core_port, access):
    """Switch di piano HPE 2930F: porte 1-24 + uplink 49 verso il core. access: {porta: [(vlan, mac)]}"""
    interfaces = {i: _iface(chassis, i, str(i), up=i in access) for i in range(1, 25)}
    interfaces[49] = _iface(chassis, 49, "49", mbps=10000, alias="Uplink core")
    interfaces[1099] = _iface(chassis, 1099, "VLAN99", if_type=53, mbps=None)
    ports = [*access, 49]
    uplink_macs = [m for m, _ in (SERVER, PC1, PC2, PC3, PC4, PC5, PRINTER, PHONE, AP)]
    local = {mac for macs in access.values() for _v, mac in macs}
    return {
        "system": _system(name, "HP J9776A 2930F-24G-4SFP+ Switch, revision WC.16.11.0012", "1.3.6.1.4.1.11.2.3.7.11.183"),
        "interfaces": interfaces,
        "ipv4": [(ip, 1099, MASK)],
        "ipv6": [],
        "entities": {1: (3, serial, "J9776A")},
        "lldp_local": {49: (5, "49", "49")},
        "lldp_remote": {(49, 1): (4, CORE_MAC, 5, core_port, f"TenGigabitEthernet{core_port[2:]}", "core-lab-01.lab.local", CORE_IP)},
        "cdp": {},
        "qbridge": True,
        "bridge_ports": {p: p for p in ports},
        "pvid": {**{p: macs[-1][0] for p, macs in access.items()}, 49: 1},
        "fdb": [
            *[(vlan, mac, port, LEARNED) for port, macs in access.items() for vlan, mac in macs],
            # Dall'uplink si vedono il core e i device degli altri piani: NetMap deve scartarli
            (99, _port_mac(CORE_MAC, 199), 49, LEARNED),
            *[(10, mac, 49, LEARNED) for mac in uplink_macs if mac not in local],
        ],
        "vlans": VLANS,
        # Porte di accesso: untagged la VLAN del PC (PVID), tagged le altre (es. voce del telefono);
        # uplink 49: untagged la VLAN 1, tagged tutte le altre
        "vlan_ports": {
            vid: (
                {p for p, macs in access.items() if vid in {v for v, _ in macs}} | {49},
                {p for p, macs in access.items() if macs[-1][0] == vid} | ({49} if vid == 1 else set()),
            )
            for vid in VLANS
        },
        "arp": [],
    }


P1 = _hpe("sw-lab-p1", P1_IP, P1_MAC, "SG23LAB001", "Te1/1/1", {
    1: [(10, PC1[0])],
    2: [(10, PC2[0])],
    24: [(10, PRINTER[0])],
})
P2 = _hpe("sw-lab-p2", P2_IP, P2_MAC, "SG23LAB002", "Te1/1/2", {
    1: [(20, PHONE[0]), (10, PC3[0])],  # telefono IP con un PC collegato dietro
    2: [(10, PC4[0])],
})

P3 = {
    "system": _system(
        "sw-lab-p3",
        "Cisco IOS Software, C1000 Software (C1000-UNIVERSALK9-M), Version 15.2(7)E8",
        "1.3.6.1.4.1.9.1.2860",
    ),
    "interfaces": {
        **{i: _iface(P3_MAC, i, f"Gi1/0/{i}", f"GigabitEthernet1/0/{i}", up=i in (1, 2)) for i in range(1, 5)},
        25: _iface(P3_MAC, 25, "Gi1/0/25", "GigabitEthernet1/0/25", alias="Uplink core"),
        199: _iface(P3_MAC, 199, "Vl99", "Vlan99", if_type=136),
    },
    "ipv4": [(P3_IP, 199, MASK)],
    "ipv6": [],
    "entities": {1: (3, "FOC2422LAB3", "C1000-24T-4G-L")},
    "lldp_local": {},
    "lldp_remote": {},
    "cdp": {(25, 1): ("core-lab-01.lab.local", "TenGigabitEthernet1/1/3", CORE_IP)},
    "cisco": {"names": CISCO_VLANS, "access": {1: 10, 2: 10}, "trunks": {25: TRUNK}},
    "qbridge": False,
    "bridge_ports": {1: 1, 2: 2, 25: 25},
    "pvid": {},
    "fdb": [
        (None, PC5[0], 1, LEARNED),
        # Access point con tre client Wi-Fi: quattro MAC sulla stessa porta
        (None, AP[0], 2, LEARNED),
        *[(None, mac, 2, LEARNED) for mac, _ in WIFI],
        (None, _port_mac(CORE_MAC, 199), 25, LEARNED),
    ],
    "vlans": {},
    "arp": [],
}

# nome del container (servizio "lab-…") -> (IP, dati)
LAB_DEVICES = {
    "fw-lab-01": (FW_IP, FW),
    "core-lab-01": (CORE_IP, CORE),
    "sw-lab-p1": (P1_IP, P1),
    "sw-lab-p2": (P2_IP, P2),
    "sw-lab-p3": (P3_IP, P3),
}
