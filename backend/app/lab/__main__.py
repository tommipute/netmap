"""Comandi della rete di laboratorio.

    python -m app.lab agent <nome>   avvia l'agent SNMP simulato di un apparato (comando dei container lab-*)
    python -m app.lab prepara        crea in NetMap sede, profilo SNMP, scansione e mappa del laboratorio
    python -m app.lab elenco         elenca gli apparati con i loro IP
"""
import os
import sys
from pathlib import Path

from app.lab.devices import COMMUNITY, LAB_DEVICES, LAB_TARGETS
from app.lab.snmprec import snmprec

SITE = "Laboratorio di rete (simulato)"
PROFILE = "Laboratorio (community public)"
JOB = "Laboratorio di rete"


def agent(name: str) -> None:
    """Scrive i dati dell'apparato e lascia il posto a snmpsim (diventa il processo principale del container)."""
    if name not in LAB_DEVICES:
        sys.exit(f"Apparato sconosciuto: {name}. Disponibili: {', '.join(LAB_DEVICES)}")
    _ip, data = LAB_DEVICES[name]
    # snmpsim gira come 'nobody': cartelle leggibili (dati) e scrivibili (cache) da tutti
    base = Path("/tmp/netmap-lab")
    data_dir, cache_dir = base / name, base / f"{name}-cache"
    for folder, mode in ((base, 0o755), (data_dir, 0o755), (cache_dir, 0o777)):
        folder.mkdir(parents=True, exist_ok=True)
        folder.chmod(mode)
    (data_dir / f"{COMMUNITY}.snmprec").write_text(snmprec(data))
    print(f"{name}: agent SNMP v2c (community {COMMUNITY}) sulla porta 161", flush=True)
    os.execvp("snmpsim-command-responder", [
        "snmpsim-command-responder", f"--data-dir={data_dir}", f"--cache-dir={cache_dir}",
        "--agent-udpv4-endpoint=0.0.0.0:161", "--process-user=nobody", "--process-group=nogroup",
    ])


def prepara() -> None:
    """Crea (se mancano) sede, profilo SNMP, scansione e mappa automatica del laboratorio."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import DiscoveryJob, NetworkMap, Site, SnmpProfile
    from app.services.rules import discovery_job_hook, snmp_profile_hook

    ips = sorted(ip for ip, _ in LAB_DEVICES.values())
    with SessionLocal() as db:
        site = db.scalars(select(Site).where(Site.name == SITE)).first()
        if site is None:
            site = Site(name=SITE, description="Apparati finti dei container lab-* (docker compose --profile lab)")
            db.add(site)
            db.flush()
        profile = db.scalars(select(SnmpProfile).where(SnmpProfile.name == PROFILE)).first()
        if profile is None:
            profile = SnmpProfile(name=PROFILE, version="v2c", port=161, timeout=2.0, retries=1,
                                  description="Profilo della rete di laboratorio")
            db.add(profile)
            snmp_profile_hook(db, profile, {"community": COMMUNITY}, True)
            db.flush()
        job = db.scalars(select(DiscoveryJob).where(DiscoveryJob.name == JOB)).first()
        if job is None:
            job = DiscoveryJob(
                name=JOB, targets=[LAB_TARGETS], profile_ids=[profile.id], site_id=site.id,
                enabled=True, interval_hours=None, auto_new_interfaces=True, auto_new_ips=True,
                description=f"Apparati di laboratorio: {', '.join(ips)}",
            )
            db.add(job)
            discovery_job_hook(db, job, {}, True)
            db.flush()
        if db.scalars(select(NetworkMap).where(NetworkMap.site_id == site.id)).first() is None:
            db.add(NetworkMap(name="Laboratorio", site_id=site.id, auto_include=True,
                              description="Tutti i device della sede di laboratorio"))
        db.commit()
        print(f"Pronto. Sede \"{SITE}\", profilo \"{PROFILE}\", scansione \"{JOB}\" (id {job.id}), mappa \"Laboratorio\".")
        print("Ora in NetMap: Scansioni -> Laboratorio di rete -> Avvia scansione.")


def elenco() -> None:
    for name, (ip, data) in LAB_DEVICES.items():
        print(f"{name:<14} {ip:<16} {data['system']['descr'][:60]}")


if __name__ == "__main__":
    command, *args = sys.argv[1:] or ["elenco"]
    if command == "agent" and len(args) == 1:
        agent(args[0])
    elif command == "prepara":
        prepara()
    elif command == "elenco":
        elenco()
    else:
        sys.exit(__doc__)
