"""Carica una piccola rete di esempio per provare API e topologia.

Uso:  docker compose exec api python -m app.seed
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    VLAN,
    Cable,
    Device,
    DeviceRole,
    DeviceType,
    Interface,
    IPAddress,
    Location,
    Manufacturer,
    NetworkMap,
    Prefix,
    Rack,
    Site,
)


def load_demo(db: Session) -> bool:
    """Carica la rete di esempio. Non fa niente (e ritorna False) se il database contiene già delle sedi."""
    if db.scalar(select(func.count(Site.id))):
        return False

    site = Site(name="Sede principale", address="Via Esempio 1")
    db.add(site)
    db.flush()

    edificio = Location(site_id=site.id, name="Edificio A")
    db.add(edificio)
    db.flush()
    ced = Location(site_id=site.id, parent_id=edificio.id, name="CED - Piano terra")
    piano1 = Location(site_id=site.id, parent_id=edificio.id, name="Primo piano")
    piano2 = Location(site_id=site.id, parent_id=edificio.id, name="Secondo piano")
    rack = Rack(site_id=site.id, name="R01")
    db.add_all([ced, piano1, piano2, rack])
    db.flush()
    rack.location_id = ced.id

    roles = {
        "firewall": DeviceRole(name="Firewall", color="#E24B4A", level=0),
        "core": DeviceRole(name="Core", color="#534AB7", level=1),
        "access": DeviceRole(name="Accesso", color="#1D9E75", level=2),
    }
    fortinet, cisco, aruba = Manufacturer(name="Fortinet"), Manufacturer(name="Cisco"), Manufacturer(name="HPE Aruba")
    db.add_all([*roles.values(), fortinet, cisco, aruba])
    db.flush()

    t_fw = DeviceType(manufacturer_id=fortinet.id, model="FortiGate 100F")
    t_core = DeviceType(manufacturer_id=cisco.id, model="Catalyst 9300-48P")
    t_access = DeviceType(manufacturer_id=aruba.id, model="2930F-48G")
    vlans = {
        vid: VLAN(site_id=site.id, vid=vid, name=name)
        for vid, name in [(10, "Uffici"), (20, "Produzione"), (99, "Management")]
    }
    db.add_all([t_fw, t_core, t_access, *vlans.values()])
    db.flush()

    def device(name, dtype, role, location, rack_position=None):
        dev = Device(
            name=name, site_id=site.id, location_id=location.id, device_type_id=dtype.id,
            role_id=roles[role].id, rack_id=rack.id if rack_position else None, rack_position=rack_position,
        )
        db.add(dev)
        db.flush()
        return dev

    def iface(dev, name, type_="copper", speed=1000, **extra):
        interface = Interface(device_id=dev.id, name=name, type=type_, speed_mbps=speed, **extra)
        db.add(interface)
        db.flush()
        return interface

    def ip(address, interface, primary=False):
        db.add(IPAddress(address=address, interface_id=interface.id, is_primary=primary))

    def cable(a, b, type_):
        db.add(Cable(a_interface_id=a.id, b_interface_id=b.id, type=type_))

    all_vlans = list(vlans.values())

    fw = device("fw-01", t_fw, "firewall", ced, rack_position=40)
    fw_lan = iface(fw, "port1")
    ip("10.10.99.254/24", iface(fw, "mgmt", mgmt_only=True), primary=True)

    core = device("core-01", t_core, "core", ced, rack_position=38)
    core_fw = iface(core, "Gi1/0/1")
    core_up1 = iface(core, "Te1/1/1", "fiber", 10000, mode="trunk")
    core_up2 = iface(core, "Te1/1/2", "fiber", 10000, mode="trunk")
    core_up1.tagged_vlans = all_vlans
    core_up2.tagged_vlans = all_vlans
    ip("10.10.99.1/24", iface(core, "Vlan99", "virtual", None), primary=True)

    switches = []
    for name, location, last_octet, access_vlan in [("sw-p1-01", piano1, 11, 10), ("sw-p2-01", piano2, 12, 20)]:
        sw = device(name, t_access, "access", location)
        uplink = iface(sw, "49", "fiber", 10000, mode="trunk")
        uplink.tagged_vlans = all_vlans
        for port in ("1", "2", "3"):
            iface(sw, port, mode="access", untagged_vlan_id=vlans[access_vlan].id)
        ip(f"10.10.99.{last_octet}/24", iface(sw, "Vlan99", "virtual", None), primary=True)
        switches.append(uplink)

    cable(fw_lan, core_fw, "cat6")
    cable(core_up1, switches[0], "fiber_mm")
    cable(core_up2, switches[1], "fiber_mm")

    for prefix, vid in [("10.10.10.0/24", 10), ("10.10.20.0/24", 20), ("10.10.99.0/24", 99)]:
        db.add(Prefix(prefix=prefix, site_id=site.id, vlan_id=vlans[vid].id))

    db.add(NetworkMap(name="Sede principale", site_id=site.id, description="Tutti i device della sede"))

    db.commit()
    return True


def run() -> None:
    with SessionLocal() as db:
        if load_demo(db):
            print("Dati di esempio caricati: 4 device, 3 cavi, 3 VLAN, 3 subnet e una mappa.")
        else:
            print("Il database contiene già dati: seed saltato.")


if __name__ == "__main__":
    run()
