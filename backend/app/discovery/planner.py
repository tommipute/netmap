"""Confronta i dati letti via SNMP con il database e decide cosa proporre.

Regole (docs/roadmap.md):
- sempre automatici, senza modifica registrata: last_seen_at, oper_status, if_index, sys_name, sys_descr
- automatici se attivati nel job: porte nuove su device esistenti, IP nuovi su porte note
- automatici: campi di oggetti creati dalla scansione (source = snmp)
- sempre da approvare: device nuovi, cavi nuovi o diversi, oggetti eliminati, campi di oggetti inseriti a mano
- stack: gli chassis della ENTITY-MIB sono i membri; quelli nuovi si aggiungono da soli (sono hardware letto dal
  device), seriale/modello cambiati seguono la regola dei campi, un membro sparito è da approvare
- VLAN: quelle lette dallo switch diventano VLAN della sede (automatiche se il job aggiunge da solo le porte
  nuove); VLAN untagged, modo access/trunk e VLAN tagged delle porte seguono la regola dei campi delle porte
"""
from dataclasses import dataclass, field
from datetime import datetime
import ipaddress

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.discovery.matching import find_device, find_port, interface_type, norm_ifname, short_name
from app.discovery.snmp import HostData, IfData
from app.discovery.vendors import vendor_name
from app.services.roles import guess_role
from app.models import VLAN, Cable, Device, DeviceRole, DeviceType, DiscoveryJob, Interface, IPAddress, StackMember
from app.models.enums import (
    NON_CABLEABLE_TYPES,
    ChangeAction,
    ChangeObject,
    InterfaceMode,
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
            new = self._new_device(hd)
            proposals = [new]
            self._vlans(self.job.site_id, hd, proposals)
            for p in proposals:
                p.device_label = new.device_label
            return proposals

        device.sys_name = hd.sys_name or device.sys_name
        device.sys_descr = hd.sys_descr or device.sys_descr
        device.last_seen_at = self.now
        device.snmp_profile_id = hd.profile_id or device.snmp_profile_id

        proposals: list[Proposal] = []
        self._device_update(device, hd, proposals)
        self._stack(device, hd, proposals)
        vlans = self._vlans(device.site_id, hd, proposals)
        ports = self._interfaces(device, hd, proposals)
        self._port_vlans(device, hd, ports, vlans, proposals)
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
            role = self.db.get(DeviceRole, known.default_role_id) if known.default_role_id else None
            return {"id": known.id, "label": known.model, "role": role.name if role else None}
        model = (hd.model or hd.sys_object_id)[:100]
        manufacturer = vendor_name(hd.sys_object_id)
        # Modello nuovo: ruolo indovinato dalla descrizione SNMP (diventa il suo ruolo predefinito)
        role = guess_role(self.db, hd.sys_descr, manufacturer, model)
        return {
            "create": {"manufacturer": manufacturer, "model": model, "sys_object_id": hd.sys_object_id,
                       "default_role_id": role.id if role else None},
            "label": f"{manufacturer} {model} (nuovo modello)",
            "role": role.name if role else None,
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
            "Ruolo": [None, type_ref.get("role") if type_ref else None],
            "Numero di serie": [None, hd.serial],
            "Stack": [None, f"{len(hd.members)} switch" if hd.members else None],
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
                "snmp_profile_id": hd.profile_id,
                "device_type": type_ref,
                "interfaces": [self._interface_data(i) for i in hd.interfaces],
                "ips": ips,
                "stack_members": [{"number": m.number, "serial": m.serial, "model": m.model} for m in hd.members],
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

    # ------------------------------------------------------------ stack
    def _stack(self, device: Device, hd: HostData, out: list[Proposal]) -> None:
        if not hd.members:
            return  # non è uno stack (o la ENTITY-MIB non lo dice): i membri inseriti a mano restano
        existing = {m.number: m for m in self.db.scalars(select(StackMember).where(StackMember.device_id == device.id))}
        for m in hd.members:
            current = existing.pop(m.number, None)
            if current is None:
                out.append(Proposal(
                    key=f"stack_member:create:{device.id}:{m.number}",
                    object_type=ChangeObject.STACK_MEMBER.value,
                    action=ChangeAction.CREATE.value,
                    summary=f"Nuovo membro {m.number} dello stack {device.name}",
                    data={"device_id": device.id, "number": m.number, "serial": m.serial, "model": m.model},
                    diff={k: v for k, v in {"Membro": [None, m.number], "Numero di serie": [None, m.serial],
                                            "Modello": [None, m.model]}.items() if v[1] not in (None, "")},
                    auto=True,
                ))
                continue
            current.last_seen_at = self.now
            data, diff = {}, {}
            if m.serial and (current.serial or "").lower() != m.serial.lower():
                data["serial"], diff["Numero di serie"] = m.serial, [current.serial, m.serial]
            if m.model and current.model != m.model:
                data["model"], diff["Modello"] = m.model, [current.model, m.model]
            if data:
                out.append(Proposal(
                    key=f"stack_member:update:{current.id}",
                    object_type=ChangeObject.STACK_MEMBER.value,
                    action=ChangeAction.UPDATE.value,
                    object_id=current.id,
                    summary=f"Membro {m.number} dello stack {device.name}: dati diversi da quelli letti via SNMP",
                    data=data,
                    diff=diff,
                    auto=current.source == SNMP or not (current.serial or current.model),
                ))
        for current in existing.values():
            out.append(Proposal(
                key=f"stack_member:stale:{current.id}",
                object_type=ChangeObject.STACK_MEMBER.value,
                action=ChangeAction.STALE.value,
                object_id=current.id,
                summary=f"Il membro {current.number} dello stack {device.name} non risulta più dalla scansione",
                data={"stack_member_id": current.id},
                diff={"Membro": [current.number, None], "Numero di serie": [current.serial, None]},
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

    # ------------------------------------------------------------ VLAN
    def _vlans(self, site_id: int, hd: HostData, out: list[Proposal]) -> set[int]:
        """Propone le VLAN che lo switch ha e NetMap no (della sede o globali). Ritorna i VID disponibili:
        quelli che esistono già e quelli appena proposti (le porte li usano dopo che la VLAN è stata creata)."""
        used = set(hd.port_vlans.values()) | {vid for vids in hd.port_tagged.values() for vid in vids}
        wanted = {vid: hd.vlans.get(vid) or f"VLAN{vid}" for vid in set(hd.vlans) | used if 2 <= vid <= 4094}
        if not wanted:
            return set()
        existing = set(self.db.scalars(
            select(VLAN.vid).where(VLAN.vid.in_(wanted), or_(VLAN.site_id == site_id, VLAN.site_id.is_(None)))
        ))
        for vid in sorted(set(wanted) - existing):
            out.append(Proposal(
                key=f"vlan:create:{site_id}:{vid}",
                object_type=ChangeObject.VLAN.value,
                action=ChangeAction.CREATE.value,
                summary=f"Nuova VLAN {vid} {wanted[vid]}",
                data={"site_id": site_id, "vid": vid, "name": wanted[vid]},
                diff={"VLAN": [None, vid], "Nome": [None, wanted[vid]]},
                auto=self.job.auto_new_interfaces,
            ))
        return set(wanted)

    def _port_vlans(self, device: Device, hd: HostData, ports: dict[int, Interface], vlans: set[int],
                    out: list[Proposal]) -> None:
        """VLAN untagged, modo (trunk se ha VLAN tagged, altrimenti access) e VLAN tagged delle porte."""
        current_vids = dict(self.db.execute(
            select(VLAN.id, VLAN.vid).where(VLAN.id.in_([p.untagged_vlan_id for p in ports.values() if p.untagged_vlan_id]))
        ).all())
        for if_index, iface in ports.items():
            if iface.type == InterfaceType.VIRTUAL.value:
                continue
            untagged = hd.port_vlans.get(if_index)
            untagged = untagged if untagged in vlans else None  # VLAN 1 di default: niente
            tagged = sorted(v for v in hd.port_tagged.get(if_index, []) if v in vlans)
            if untagged is None and not tagged:
                continue
            mode = InterfaceMode.TRUNK.value if tagged else InterfaceMode.ACCESS.value
            now_untagged = current_vids.get(iface.untagged_vlan_id)
            now_tagged = sorted(v.vid for v in iface.tagged_vlans)
            if (iface.mode, now_untagged, now_tagged) == (mode, untagged, tagged):
                continue
            diff = {}
            if iface.mode != mode:
                diff["Modo"] = [iface.mode, mode]
            if now_untagged != untagged:
                diff["VLAN untagged"] = [now_untagged, untagged]
            if now_tagged != tagged:
                diff["VLAN tagged"] = [", ".join(map(str, now_tagged)) or None, ", ".join(map(str, tagged)) or None]
            out.append(Proposal(
                key=f"interface:vlans:{iface.id}",
                object_type=ChangeObject.INTERFACE.value,
                action=ChangeAction.UPDATE.value,
                object_id=iface.id,
                summary=f"Porta {_port_label(device, iface)}: VLAN lette dallo switch",
                data={"mode": mode, "untagged_vid": untagged, "tagged_vids": tagged, "vlan_site_id": device.site_id},
                diff=diff,
                auto=iface.source == SNMP,
            ))

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
