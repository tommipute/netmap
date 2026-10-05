"""Confronta i dati letti via SNMP con il database e decide cosa proporre.

Regole (docs/roadmap.md):
- sempre automatici, senza modifica registrata: last_seen_at, oper_status, if_index, sys_name, sys_descr
- automatici se attivati nel job: porte nuove su device esistenti, IP nuovi su porte note
- automatici: campi di oggetti creati dalla scansione (source = snmp)
- sempre da approvare: device nuovi, cavi nuovi o diversi, oggetti eliminati, campi di oggetti inseriti a mano
"""
from dataclasses import dataclass, field
from datetime import datetime
import ipaddress

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.discovery.matching import find_device, find_port, interface_type, norm_ifname, short_name
from app.discovery.snmp import HostData, IfData
from app.discovery.vendors import vendor_name
from app.models import Cable, Device, DeviceType, DiscoveryJob, Interface, IPAddress
from app.models.enums import (
    NON_CABLEABLE_TYPES,
    ChangeAction,
    ChangeObject,
    InterfaceType,
    Source,
)

SNMP = Source.SNMP.value


@dataclass
class Proposal:
    key: str
    object_type: str
    action: str
    summary: str
    data: dict
    diff: dict = field(default_factory=dict)  # {campo: [attuale, proposto]} con valori leggibili
    auto: bool = False
    object_id: int | None = None
    device_id: int | None = None
    device_label: str = ""


def _port_label(device: Device, iface: Interface) -> str:
    return f"{device.name} {iface.name}"


class Planner:
    def __init__(self, db: Session, job: DiscoveryJob, now: datetime):
        self.db, self.job, self.now = db, job, now

    # ------------------------------------------------------------ ingresso
    def plan(self, hd: HostData) -> list[Proposal]:
        device = find_device(
            self.db,
            serial=hd.serial,
            sys_name=hd.sys_name,
            ips=[hd.host, *(ip.address for ip in hd.ips)],
        )
        if device is None:
            return [self._new_device(hd)]

        device.sys_name = hd.sys_name or device.sys_name
        device.sys_descr = hd.sys_descr or device.sys_descr
        device.last_seen_at = self.now

        proposals: list[Proposal] = []
        self._device_update(device, hd, proposals)
        ports = self._interfaces(device, hd, proposals)
        self._ips(device, hd, ports, proposals)
        self._neighbors(device, hd, ports, proposals)
        for p in proposals:
            p.device_id = p.device_id or device.id
            p.device_label = p.device_label or device.name
        return proposals

    # ------------------------------------------------------------ device
    def _device_type_ref(self, hd: HostData) -> dict | None:
        """{"id": ..} se il sysObjectID è di un modello noto, {"create": {..}} per proporne uno nuovo."""
        if not hd.sys_object_id:
            return None
        known = self.db.scalars(select(DeviceType).where(DeviceType.sys_object_id == hd.sys_object_id)).first()
        if known:
            return {"id": known.id, "label": known.model}
        model = (hd.model or hd.sys_object_id)[:100]
        manufacturer = vendor_name(hd.sys_object_id)
        return {
            "create": {"manufacturer": manufacturer, "model": model, "sys_object_id": hd.sys_object_id},
            "label": f"{manufacturer} {model} (nuovo modello)",
        }

    def _new_device(self, hd: HostData) -> Proposal:
        name = (short_name(hd.sys_name) or hd.host)[:100]
        type_ref = self._device_type_ref(hd)
        if_indexes = {i.if_index for i in hd.interfaces}
        ips = [
            {"address": ip.address, "if_index": ip.if_index, "is_primary": ipaddress.ip_interface(ip.address).ip == ipaddress.ip_address(hd.host)}
            for ip in hd.ips
            if ip.if_index in if_indexes
        ]
        details = {
            "Indirizzo scansionato": [None, hd.host],
            "Modello": [None, type_ref["label"] if type_ref else None],
            "Numero di serie": [None, hd.serial],
            "Porte": [None, len(hd.interfaces)],
            "IP": [None, ", ".join(ip["address"] for ip in ips) or None],
            "Posizione SNMP": [None, hd.sys_location],
        }
        return Proposal(
            key=f"device:create:{(hd.serial or short_name(hd.sys_name) or hd.host).lower()}",
            object_type=ChangeObject.DEVICE.value,
            action=ChangeAction.CREATE.value,
            summary=f"Nuovo device {name} ({hd.host}) con {len(hd.interfaces)} porte",
            data={
                "name": name,
                "site_id": self.job.site_id,
                "serial": hd.serial,
                "sys_name": hd.sys_name,
                "sys_descr": hd.sys_descr,
                "device_type": type_ref,
                "interfaces": [self._interface_data(i) for i in hd.interfaces],
                "ips": ips,
            },
            diff={k: v for k, v in details.items() if v[1] not in (None, "")},
            device_label=name,
        )

    def _device_update(self, device: Device, hd: HostData, out: list[Proposal]) -> None:
        data, diff = {}, {}
        if hd.serial and (device.serial or "").lower() != hd.serial.lower():
            data["serial"], diff["Numero di serie"] = hd.serial, [device.serial, hd.serial]

        type_ref = self._device_type_ref(hd)
        if type_ref:
            current = self.db.get(DeviceType, device.device_type_id) if device.device_type_id else None
            # Modello mancante, oppure il sysObjectID indica un altro modello già censito
            if current is None or (type_ref.get("id") not in (None, current.id)):
                data["device_type"] = type_ref
                diff["Modello"] = [current.model if current else None, type_ref["label"]]

        if data:
            out.append(Proposal(
                key=f"device:update:{device.id}",
                object_type=ChangeObject.DEVICE.value,
                action=ChangeAction.UPDATE.value,
                object_id=device.id,
                summary=f"Dati di {device.name} diversi da quelli letti via SNMP",
                data=data,
                diff=diff,
                auto=device.source == SNMP,
            ))

    # ------------------------------------------------------------ porte
    @staticmethod
    def _interface_data(i: IfData) -> dict:
        return {
            "name": i.name,
            "if_index": i.if_index,
            "type": interface_type(i.if_type),
            "speed_mbps": i.speed_mbps,
            "mac_address": i.mac,
            "mtu": i.mtu,
            "enabled": i.admin_up if i.admin_up is not None else True,
            "description": i.alias,
            "oper_status": i.oper_status,
        }

    def _interfaces(self, device: Device, hd: HostData, out: list[Proposal]) -> dict[int, Interface]:
        existing = list(self.db.scalars(select(Interface).where(Interface.device_id == device.id)))
        by_index = {i.if_index: i for i in existing if i.if_index is not None}
        cabled = self._cabled_ids([i.id for i in existing])
        matched: dict[int, Interface] = {}  # ifIndex letto -> porta nel database
        used: set[int] = set()

        for d in hd.interfaces:
            by_name = find_port(existing, names=[d.name, d.descr])
            by_idx = by_index.get(d.if_index)
            # ifIndex prima del nome, a meno che il nome indichi chiaramente un'altra porta
            iface = by_idx if by_idx and (by_name is None or by_name is by_idx) else (by_name or by_idx)
            if iface is not None and iface.id in used:
                iface = None
            if iface is None:
                out.append(Proposal(
                    key=f"interface:create:{device.id}:{norm_ifname(d.name)}",
                    object_type=ChangeObject.INTERFACE.value,
                    action=ChangeAction.CREATE.value,
                    summary=f"Nuova porta {d.name} su {device.name}",
                    data={"device_id": device.id, **self._interface_data(d)},
                    diff={k: v for k, v in {
                        "Porta": [None, d.name],
                        "Velocità (Mbps)": [None, d.speed_mbps],
                        "MAC": [None, d.mac],
                        "Descrizione": [None, d.alias],
                    }.items() if v[1] not in (None, "")},
                    auto=self.job.auto_new_interfaces,
                ))
                continue

            used.add(iface.id)
            matched[d.if_index] = iface
            iface.if_index = d.if_index
            iface.oper_status = d.oper_status
            iface.last_seen_at = self.now

            data, diff = self._interface_diff(iface, d, iface.id in cabled)
            if data:
                out.append(Proposal(
                    key=f"interface:update:{iface.id}",
                    object_type=ChangeObject.INTERFACE.value,
                    action=ChangeAction.UPDATE.value,
                    object_id=iface.id,
                    summary=f"Porta {_port_label(device, iface)}: dati diversi da quelli letti via SNMP",
                    data=data,
                    diff=diff,
                    auto=iface.source == SNMP,
                ))

        # Porte già viste da una scansione (hanno l'ifIndex) che ora non ci sono più
        for iface in existing:
            if iface.id in used or iface.if_index is None:
                continue
            note = " (ha un cavo: verrà eliminato anche quello)" if iface.id in cabled else ""
            out.append(Proposal(
                key=f"interface:stale:{iface.id}",
                object_type=ChangeObject.INTERFACE.value,
                action=ChangeAction.STALE.value,
                object_id=iface.id,
                summary=f"La porta {_port_label(device, iface)} non risulta più dalla scansione{note}",
                data={"interface_id": iface.id},
                diff={"Porta": [iface.name, None]},
            ))
        return matched

    @staticmethod
    def _interface_diff(iface: Interface, d: IfData, cabled: bool) -> tuple[dict, dict]:
        data, diff = {}, {}

        def change(column: str, label: str, value) -> None:
            data[column] = value
            diff[label] = [getattr(iface, column), value]

        if d.name and norm_ifname(d.name) != norm_ifname(iface.name):
            change("name", "Nome", d.name)
        # La velocità di una porta spenta non dice niente: si propone solo se manca o se la porta è su
        if d.speed_mbps and iface.speed_mbps != d.speed_mbps and (iface.speed_mbps is None or d.oper_status == "up"):
            change("speed_mbps", "Velocità (Mbps)", d.speed_mbps)
        if d.mac and iface.mac_address != d.mac:
            change("mac_address", "MAC", d.mac)
        if d.mtu and iface.mtu != d.mtu:
            change("mtu", "MTU", d.mtu)
        if d.admin_up is not None and iface.enabled != d.admin_up:
            change("enabled", "Abilitata", d.admin_up)
        if d.alias and (iface.description or "") != d.alias:
            change("description", "Descrizione", d.alias)
        detected = interface_type(d.if_type)
        if detected in (InterfaceType.LAG.value, InterfaceType.VIRTUAL.value, InterfaceType.WIRELESS.value):
            if iface.type != detected and not (cabled and detected in NON_CABLEABLE_TYPES):
                change("type", "Tipo", detected)
        return data, diff

    def _cabled_ids(self, interface_ids: list[int]) -> set[int]:
        if not interface_ids:
            return set()
        rows = self.db.execute(
            select(Cable.a_interface_id, Cable.b_interface_id).where(
                or_(Cable.a_interface_id.in_(interface_ids), Cable.b_interface_id.in_(interface_ids))
            )
        ).all()
        return {i for row in rows for i in row} & set(interface_ids)

    # ------------------------------------------------------------ IP
    def _ips(self, device: Device, hd: HostData, ports: dict[int, Interface], out: list[Proposal]) -> None:
        port_ids = [p.id for p in ports.values()]
        has_primary = bool(port_ids) and self.db.scalar(
            select(IPAddress.id).where(IPAddress.interface_id.in_(port_ids), IPAddress.is_primary.is_(True))
        ) is not None
        scanned = ipaddress.ip_address(hd.host)

        for ip_data in hd.ips:
            iface = ports.get(ip_data.if_index)
            if iface is None:
                continue  # porta nuova non ancora approvata: l'IP arriverà alla prossima scansione
            host = ipaddress.ip_interface(ip_data.address).ip
            primary = not has_primary and host == scanned
            label = _port_label(device, iface)
            ip = self.db.scalars(
                select(IPAddress).where(IPAddress.host == str(host), IPAddress.vrf_id.is_(None))
            ).first()

            if ip is None:
                out.append(Proposal(
                    key=f"ip:create:{host}",
                    object_type=ChangeObject.IP.value,
                    action=ChangeAction.CREATE.value,
                    summary=f"Nuovo IP {ip_data.address} su {label}",
                    data={"address": ip_data.address, "interface_id": iface.id, "is_primary": primary},
                    diff={"Indirizzo": [None, ip_data.address], "Porta": [None, label]},
                    auto=self.job.auto_new_ips,
                ))
                continue

            ip.last_seen_at = self.now
            data, diff = {}, {}
            if ip.interface_id != iface.id:
                current = _port_label(ip.interface.device, ip.interface) if ip.interface else None
                data["interface_id"], diff["Porta"] = iface.id, [current, label]
            if ip.address != ip_data.address:
                data["address"], diff["Indirizzo"] = ip_data.address, [ip.address, ip_data.address]
            if primary and not ip.is_primary:
                data["is_primary"], diff["IP di management"] = True, [False, True]
            if data:
                out.append(Proposal(
                    key=f"ip:update:{ip.id}",
                    object_type=ChangeObject.IP.value,
                    action=ChangeAction.UPDATE.value,
                    object_id=ip.id,
                    summary=f"IP {ip.address}: la scansione lo vede su {label}",
                    data=data,
                    diff=diff,
                    auto=ip.source == SNMP,
                ))

    # ------------------------------------------------------------ cavi (LLDP / CDP)
    def _cable_of(self, interface_id: int) -> Cable | None:
        return self.db.scalars(
            select(Cable).where(or_(Cable.a_interface_id == interface_id, Cable.b_interface_id == interface_id))
        ).first()

    def _neighbors(self, device: Device, hd: HostData, ports: dict[int, Interface], out: list[Proposal]) -> None:
        seen: set[str] = set()
        for n in hd.neighbors:
            local = ports.get(n.local_if_index)
            if local is None or local.type in NON_CABLEABLE_TYPES:
                continue
            remote_device = find_device(self.db, sys_name=n.sys_name, ips=n.addresses, macs=[n.chassis_mac])
            if remote_device is None or remote_device.id == device.id:
                continue
            remote_ports = list(self.db.scalars(select(Interface).where(Interface.device_id == remote_device.id)))
            remote = find_port(
                remote_ports,
                names=[n.port_id, n.port_descr] if n.port_id_type != "mac" else [n.port_descr],
                mac=n.port_id if n.port_id_type == "mac" else None,
                if_index=int(n.port_id) if n.port_id_type == "local" and (n.port_id or "").isdigit() else None,
            )
            if remote is None or remote.type in NON_CABLEABLE_TYPES:
                continue

            key = f"cable:{min(local.id, remote.id)}-{max(local.id, remote.id)}"
            if key in seen:
                continue  # stesso collegamento visto sia da LLDP sia da CDP
            seen.add(key)

            local_cable, remote_cable = self._cable_of(local.id), self._cable_of(remote.id)
            if local_cable is not None and local_cable is remote_cable:
                local_cable.last_seen_at = self.now
                continue

            # Verso fisso (porta con id minore come lato A): lo stesso cavo visto dai due lati è identico
            (a_dev, a), (b_dev, b) = sorted([(device, local), (remote_device, remote)], key=lambda end: end[1].id)
            link = f"{_port_label(a_dev, a)} ↔ {_port_label(b_dev, b)}"
            data = {"a_interface_id": a.id, "b_interface_id": b.id}
            if local_cable is None and remote_cable is None:
                out.append(Proposal(
                    key=key,
                    object_type=ChangeObject.CABLE.value,
                    action=ChangeAction.CREATE.value,
                    summary=f"Nuovo collegamento {link} (visto via {n.protocol.upper()})",
                    data=data,
                    diff={"Collegamento": [None, link]},
                ))
                continue

            replaced = [c for c in (local_cable, remote_cable) if c is not None]
            current = "; ".join(
                f"{c.a_device_name} {c.a_interface_name} ↔ {c.b_device_name} {c.b_interface_name}" for c in replaced
            )
            out.append(Proposal(
                key=key,
                object_type=ChangeObject.CABLE.value,
                action=ChangeAction.UPDATE.value,
                object_id=replaced[0].id,
                summary=f"Collegamento diverso: via {n.protocol.upper()} si vede {link}",
                data={**data, "remove_cable_ids": [c.id for c in replaced]},
                diff={"Collegamento": [current, link]},
            ))
