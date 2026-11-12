"""Come è installato NetMap, per la pagina Aggiornamenti e il pacchetto diagnostico.

L'app non vede l'host, quindi lo deduce da quello che c'è nel container:
- server: lo script di aggiornamento (updater/) gira e ha scritto status.json, con la sua modalità (docker, image, vm).
  Se tace da più di STALE_DAYS conta come manuale (cartella copiata da un server, script tolto, prove vecchie), e
  stale_updater fa comparire un avviso: un timer rotto su un server vero si vede da lì;
- altrimenti è un'installazione manuale, da aggiornare con i comandi mostrati nella pagina. Da dove viene il codice:
  image = immagini pronte (/app/deploy c'è solo nello stadio release del Dockerfile), archive = zip o tar.gz scaricato
  da GitHub (archive.txt: GitHub sostituisce il segnaposto negli archivi, `export-subst` in .gitattributes),
  git = tutto il resto (un clone del repository).
Il sistema dell'host si vede dal kernel: Docker Desktop su Windows usa quello di WSL2, su Mac quello di LinuxKit.
"""

import platform
from pathlib import Path

from app.services import updater

STALE_DAYS = 7
APP_DIR = Path(__file__).resolve().parents[1]  # cartella app/
ARCHIVE_FILE = APP_DIR / "archive.txt"
DEPLOY_DIR = APP_DIR.parent / "deploy"


def archive_info() -> dict | None:
    """Commit e data scritti da GitHub nell'archivio; None in un clone git (resta il segnaposto $Format)."""
    try:
        text = ARCHIVE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    parts = text.split()
    if len(parts) != 2 or "$" in text:
        return None
    return {"commit": parts[0], "date": parts[1]}


def host_system() -> str:
    kernel = platform.release().lower()
    if "microsoft" in kernel or "wsl" in kernel:
        return "windows"
    if "linuxkit" in kernel:
        return "mac"
    return "linux"


def source() -> str:
    if DEPLOY_DIR.is_dir():
        return "image"
    return "archive" if archive_info() else "git"


def info() -> dict:
    status = updater.read_json("status.json") or {}
    mode = (status.get("updater") or {}).get("mode")
    silent = updater.minutes_since(status.get("last_run"))
    stale = bool(mode) and (silent is None or silent > STALE_DAYS * 24 * 60)
    return {
        "kind": "server" if mode and not stale else "manual",
        "updater_mode": mode,
        "stale_updater": stale,
        "updater_last_run": status.get("last_run") if stale else None,
        "source": source(),
        "host": host_system(),
        "archive": archive_info(),
    }
