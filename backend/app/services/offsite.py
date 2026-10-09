"""Copie dei backup fuori dal server (cartella di rete SMB o SFTP) e ritorno di un file sul server.

I backup li fa lo script sull'host (updater/updater.sh) nella cartella montata in /backups; qui si copiano soltanto.
Il lavoro lo fa un thread del worker (offsite_loop): copia i file nuovi su ogni destinazione attiva, cancella quelli
vecchi dalla destinazione ed esegue le richieste dell'interfaccia (BackupTask: "copia ora", "riporta sul server").
Password e chiavi stanno cifrate nel database (core/secrets.py).
"""
import base64
import hashlib
import io
import logging
import os
import re
import shutil
import socket
import stat
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.secrets import SecretError, decrypt, master_key
from app.models import BackupCopy, BackupTarget, BackupTask

logger = logging.getLogger("netmap.offsite")

# File di backup (nella cartella e sulle destinazioni); si copiano tutti tranne quelli caricati o riportati qui
BACKUP_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,200}\.dump")
COPIED = re.compile(r"(daily|manual|netmap|before-restore)-[A-Za-z0-9._-]*\.dump")
KEY_FILE = re.compile(r"netmap-secrets-[0-9a-f]{12}\.key")
DATE_IN_NAME = re.compile(r"-(\d{8}-\d{6})")
DUMP_MAGIC = b"PGDMP"  # inizio dei file di pg_dump -Fc
SETTLE_SECONDS = 30  # un file appena cambiato potrebbe essere ancora in scrittura
TIMEOUT = 20
POLL_SECONDS = 5  # richieste dall'interfaccia
SCAN_SECONDS = 60  # file nuovi da copiare
RETRY_MINUTES = 15  # dopo un errore si riprova da soli dopo questo tempo


class OffsiteError(Exception):
    pass


@dataclass
class RemoteFile:
    name: str
    size: int
    date: datetime | None  # ora locale, senza fuso


def backup_dir() -> Path:
    return Path(settings.backup_dir)


def mounted() -> bool:
    return backup_dir().is_dir()


def local_files() -> list[Path]:
    """Backup nella cartella, dal più recente."""
    if not mounted():
        return []
    files = [p for p in backup_dir().iterdir() if BACKUP_NAME.fullmatch(p.name) and p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def key_file_name() -> str:
    """Nome della copia della chiave dei segreti: cambia con la chiave, così i backup vecchi trovano la loro."""
    return f"netmap-secrets-{hashlib.sha256(master_key().encode()).hexdigest()[:12]}.key"


def name_date(name: str) -> datetime | None:
    match = DATE_IN_NAME.search(name)
    try:
        return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S") if match else None
    except ValueError:
        return None


def host_key_fingerprint(host_key: str | None) -> str | None:
    """"ssh-ed25519 AAAA..." -> "SHA256:..." come lo mostra ssh-keygen -l."""
    if not host_key or " " not in host_key:
        return None
    try:
        raw = base64.b64decode(host_key.split(" ", 1)[1])
    except ValueError:
        return None
    return "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip("=")


def _name_error(text: str) -> bool:
    return "Name or service not known" in text or "name resolution" in text or "nodename nor servname" in text


# --------------------------------------------------------------------------------------------- destinazioni
class Remote:
    """Una cartella su un'altra macchina: elenco, copia avanti e indietro, cancellazione."""

    seen_host_key: str | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def list(self) -> list[RemoteFile]:
        raise NotImplementedError

    def upload(self, source, name: str) -> None:
        """source: percorso o file aperto in lettura binaria."""
        raise NotImplementedError

    def download(self, name: str, target) -> None:
        """target: file aperto in scrittura binaria."""
        raise NotImplementedError

    def delete(self, name: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


def _open_source(source):
    return open(source, "rb") if isinstance(source, (str, Path)) else source


class SmbRemote(Remote):
    def __init__(self, target: BackupTarget, password: str | None):
        import smbclient

        self.smb = smbclient
        self.cache: dict = {}
        self.host = target.host
        self.port = port = target.port or 445
        self.share = share = (target.share or "").strip("/\\")
        if not share:
            raise OffsiteError("Manca il nome della condivisione")
        folder = target.folder.strip("/\\").replace("/", "\\")
        self.base = rf"\\{target.host}\{share}" + (f"\\{folder}" if folder else "")
        self.kw = {"username": target.username, "password": password or "", "port": port,
                   "connection_cache": self.cache, "connection_timeout": TIMEOUT}
        try:
            smbclient.register_session(target.host, **self.kw)
            if folder:
                smbclient.makedirs(self.base, exist_ok=True, **self.kw)
            else:
                smbclient.stat(self.base, **self.kw)
        except Exception as exc:
            self.close()
            raise OffsiteError(self._message(exc)) from exc

    def _message(self, exc: Exception) -> str:
        """Errori di smbprotocol in parole: il codice NT sta nel testo (STATUS_...) o nel nome della classe."""
        text = f"{type(exc).__name__} {exc}"
        if "LOGON_FAILURE" in text or "LogonFailure" in text or "SpnegoError" in text:
            return "Nome utente o password sbagliati"
        if "BAD_NETWORK_NAME" in text or "BadNetworkName" in text:
            return f"La condivisione {self.share} non esiste su {self.host}"
        if "ACCESS_DENIED" in text or "AccessDenied" in text:
            return "Accesso negato: l'utente non può scrivere in quella cartella"
        if "NOT_FOUND" in text or "NotFound" in text or "No such file" in text:
            return "La cartella non esiste e non si può creare"
        if _name_error(text):
            return f"Il nome {self.host} non si trova (DNS): prova con l'indirizzo IP"
        if isinstance(exc, (ValueError, ConnectionError, TimeoutError)) and ("connect" in text.lower() or "timed out" in text):
            return f"Il server {self.host} non risponde sulla porta {self.port}"
        return f"Errore SMB: {exc}"

    def _path(self, name: str) -> str:
        return f"{self.base}\\{name}"

    def _wrap(self, action, *args):
        try:
            return action(*args)
        except OffsiteError:
            raise
        except Exception as exc:
            raise OffsiteError(self._message(exc)) from exc

    def list(self) -> list[RemoteFile]:
        def scan():
            files = []
            for entry in self.smb.scandir(self.base, **self.kw):
                if entry.is_file():
                    info = entry.stat()
                    files.append(RemoteFile(entry.name, info.st_size, datetime.fromtimestamp(info.st_mtime)))
            return files

        return self._wrap(scan)

    def upload(self, source, name: str) -> None:
        def copy():
            temp = self._path(f".{name}.part")
            with _open_source(source) as src, self.smb.open_file(temp, mode="wb", **self.kw) as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            self.smb.replace(temp, self._path(name), **self.kw)

        self._wrap(copy)

    def download(self, name: str, target) -> None:
        def copy():
            with self.smb.open_file(self._path(name), mode="rb", **self.kw) as src:
                shutil.copyfileobj(src, target, 1024 * 1024)

        self._wrap(copy)

    def delete(self, name: str) -> None:
        self._wrap(lambda: self.smb.remove(self._path(name), **self.kw))

    def close(self) -> None:
        self.smb.reset_connection_cache(fail_on_error=False, connection_cache=self.cache)


def load_private_key(text: str):
    import paramiko

    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(text.strip() + "\n"))
        except (paramiko.SSHException, ValueError, IndexError):
            continue
    raise OffsiteError("La chiave privata non si legge: serve una chiave OpenSSH o PEM senza passphrase")


class SftpRemote(Remote):
    def __init__(self, target: BackupTarget, password: str | None, private_key: str | None):
        import paramiko

        self.transport = None
        port = target.port or 22
        try:
            sock = socket.create_connection((target.host, port), timeout=TIMEOUT)
        except OSError as exc:
            if _name_error(str(exc)):
                raise OffsiteError(f"Il nome {target.host} non si trova (DNS): prova con l'indirizzo IP") from exc
            raise OffsiteError(f"Il server {target.host} non risponde sulla porta {port}") from exc
        try:
            self.transport = paramiko.Transport(sock)
            self.transport.banner_timeout = TIMEOUT
            self.transport.auth_timeout = TIMEOUT
            self.transport.start_client(timeout=TIMEOUT)
            key = self.transport.get_remote_server_key()
            self.seen_host_key = f"{key.get_name()} {key.get_base64()}"
            # La prima volta la chiave del server si registra; poi deve restare quella (niente server finti in mezzo)
            if target.host_key and target.host_key != self.seen_host_key:
                raise OffsiteError(
                    f"La chiave del server SFTP è cambiata (ora {host_key_fingerprint(self.seen_host_key)}, registrata "
                    f"{host_key_fingerprint(target.host_key)}). Se il server è stato reinstallato, nella destinazione "
                    "scegli «Accetta la nuova chiave del server»"
                )
            if private_key:
                self.transport.auth_publickey(target.username, load_private_key(private_key))
            else:
                self.transport.auth_password(target.username, password or "")
            self.sftp = paramiko.SFTPClient.from_transport(self.transport)
            self.sftp.get_channel().settimeout(120)
            self.base = self._prepare(target.folder.strip())
        except OffsiteError:
            self.close()
            raise
        except paramiko.AuthenticationException as exc:
            self.close()
            raise OffsiteError("Nome utente, password o chiave sbagliati") from exc
        except (paramiko.SSHException, OSError, EOFError) as exc:
            self.close()
            raise OffsiteError(f"Errore SFTP: {exc or type(exc).__name__}") from exc

    def _prepare(self, folder: str) -> str:
        """Crea la cartella se manca (un pezzo alla volta) e la restituisce."""
        if not folder or folder in (".", "/"):
            return folder or "."
        current = "/" if folder.startswith("/") else ""
        for part in [p for p in folder.split("/") if p]:
            current = f"{current}{part}" if current in ("", "/") else f"{current}/{part}"
            try:
                if not stat.S_ISDIR(self.sftp.stat(current).st_mode):
                    raise OffsiteError(f"{current} non è una cartella")
            except FileNotFoundError:
                try:
                    self.sftp.mkdir(current)
                except OSError as exc:
                    raise OffsiteError(f"Non riesco a creare la cartella {current}: {exc}") from exc
        return folder

    def _path(self, name: str) -> str:
        return f"{self.base.rstrip('/')}/{name}" if self.base != "." else name

    def _wrap(self, action, *args):
        try:
            return action(*args)
        except OffsiteError:
            raise
        except PermissionError as exc:
            raise OffsiteError("Accesso negato: l'utente non può scrivere in quella cartella") from exc
        except Exception as exc:
            raise OffsiteError(f"Errore SFTP: {exc or type(exc).__name__}") from exc

    def list(self) -> list[RemoteFile]:
        return self._wrap(lambda: [
            RemoteFile(a.filename, a.st_size or 0, datetime.fromtimestamp(a.st_mtime) if a.st_mtime else None)
            for a in self.sftp.listdir_attr(self.base) if a.st_mode is not None and stat.S_ISREG(a.st_mode)
        ])

    def upload(self, source, name: str) -> None:
        def copy():
            temp, final = self._path(f".{name}.part"), self._path(name)
            with _open_source(source) as src:
                self.sftp.putfo(src, temp, confirm=True)
            try:
                self.sftp.posix_rename(temp, final)
            except OSError:  # server senza l'estensione posix-rename: tolgo il vecchio e rinomino
                try:
                    self.sftp.remove(final)
                except OSError:
                    pass
                self.sftp.rename(temp, final)

        self._wrap(copy)

    def download(self, name: str, target) -> None:
        self._wrap(lambda: self.sftp.getfo(self._path(name), target))

    def delete(self, name: str) -> None:
        self._wrap(lambda: self.sftp.remove(self._path(name)))

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()


def connect(target: BackupTarget) -> Remote:
    try:
        password = decrypt(target.secret_enc) if target.secret_enc else None
        private_key = decrypt(target.private_key_enc) if target.private_key_enc else None
    except SecretError as exc:
        raise OffsiteError(
            "La password salvata non si legge più: la chiave dei segreti è cambiata. Reinseriscila nella destinazione "
            "o usa la chiave del vecchio server (pagina Backup)"
        ) from exc
    if target.type == "smb":
        return SmbRemote(target, password)
    if target.type == "sftp":
        return SftpRemote(target, password, private_key)
    raise OffsiteError(f"Tipo di destinazione sconosciuto: {target.type}")


def remember_host_key(target: BackupTarget, remote: Remote) -> None:
    if remote.seen_host_key and not target.host_key:
        target.host_key = remote.seen_host_key


# ------------------------------------------------------------------------------------------------- lavoro
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _settled(path: Path) -> bool:
    return time.time() - path.stat().st_mtime > SETTLE_SECONDS


def _expired(target: BackupTarget, name: str, date: datetime | None = None) -> bool:
    """Più vecchio di quanto la destinazione tiene le copie."""
    when = name_date(name) or date
    return bool(target.keep_days > 0 and when and when < datetime.now() - timedelta(days=target.keep_days))


def pending(db: Session, target: BackupTarget) -> list[Path]:
    """Backup della cartella non ancora copiati su questa destinazione (non quelli che verrebbero subito cancellati)."""
    done = {row.file: row.size for row in db.scalars(select(BackupCopy).where(BackupCopy.target_id == target.id))}
    return [
        p for p in local_files()
        if COPIED.fullmatch(p.name) and _settled(p) and done.get(p.name) != p.stat().st_size
        and not _expired(target, p.name, datetime.fromtimestamp(p.stat().st_mtime))
    ]


def sync(db: Session, target: BackupTarget) -> str:
    """Copia i backup che mancano, la chiave (se richiesto) e cancella dalla destinazione quelli troppo vecchi."""
    if not mounted():
        raise OffsiteError("La cartella dei backup non è montata nel container (vedi README, Backup)")
    todo = pending(db, target)
    copied = deleted = 0
    with connect(target) as remote:
        remember_host_key(target, remote)
        there = {f.name: f for f in remote.list()}
        for path in todo:
            size = path.stat().st_size
            if there.get(path.name) is None or there[path.name].size != size:
                logger.info("Copio %s su %s", path.name, target.name)
                remote.upload(path, path.name)
                copied += 1
            row = db.scalar(select(BackupCopy).where(BackupCopy.target_id == target.id, BackupCopy.file == path.name))
            if row is None:
                db.add(BackupCopy(target_id=target.id, file=path.name, size=size, copied_at=_now()))
            else:
                row.size, row.copied_at = size, _now()
            there[path.name] = RemoteFile(path.name, size, datetime.now())
            db.commit()
        if target.include_key and key_file_name() not in there:
            remote.upload(io.BytesIO(master_key().encode() + b"\n"), key_file_name())
        if target.keep_days > 0:
            for name, info in list(there.items()):
                if COPIED.fullmatch(name) and _expired(target, name, info.date):
                    remote.delete(name)
                    del there[name]
                    deleted += 1
        # Righe di file che non ci sono più né qui né sulla destinazione
        local = {p.name for p in local_files()}
        for row in db.scalars(select(BackupCopy).where(BackupCopy.target_id == target.id)).all():
            if row.file not in local and row.file not in there:
                db.delete(row)
    target.last_copy_at = _now()
    target.last_error = None
    target.last_error_at = None
    db.commit()
    parts = [f"{copied} file copiati" if copied != 1 else "1 file copiato"]
    if deleted:
        parts.append(f"{deleted} vecchi cancellati" if deleted != 1 else "1 vecchio cancellato")
    return ", ".join(parts)


def imported_name(name: str) -> str:
    return name if name.startswith("imported-") else f"imported-{name}"


def publish(temp: Path, name: str) -> Path:
    """Un file scritto per intero in temp (caricato o riportato) diventa un backup della cartella, se lo è davvero."""
    try:
        with temp.open("rb") as src:
            head = src.read(len(DUMP_MAGIC))
        if not head:
            raise OffsiteError("Il file è vuoto")
        if head != DUMP_MAGIC:
            raise OffsiteError("Il file non è un backup di NetMap (pg_dump in formato custom)")
        os.chmod(temp, 0o644)  # lo script sull'host gira con un altro utente e lo deve leggere
        final = backup_dir() / name
        os.replace(temp, final)
        return final
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def fetch(db: Session, target: BackupTarget, name: str) -> str:
    """Riporta un backup dalla destinazione nella cartella del server (come imported-...)."""
    if not BACKUP_NAME.fullmatch(name):
        raise OffsiteError("Nome del file non valido")
    if not mounted():
        raise OffsiteError("La cartella dei backup non è montata nel container (vedi README, Backup)")
    dest = imported_name(name)
    if (backup_dir() / dest).exists():
        raise OffsiteError(f"Sul server c'è già {dest}")
    temp = backup_dir() / f".{dest}.part"
    try:
        with connect(target) as remote:
            remember_host_key(target, remote)
            with temp.open("wb") as out:
                remote.download(name, out)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    publish(temp, dest)
    db.commit()
    return dest


def read_key(target: BackupTarget, name: str) -> str:
    """Contenuto di una copia della chiave dei segreti sulla destinazione."""
    if not KEY_FILE.fullmatch(name):
        raise OffsiteError("Non è una copia della chiave dei segreti")
    buffer = io.BytesIO()
    with connect(target) as remote:
        remote.download(name, buffer)
    return buffer.getvalue().decode("ascii", errors="replace").strip()


def test(db: Session, target: BackupTarget) -> dict:
    """Prova di connessione: elenca la cartella, scrive e cancella un file di prova."""
    with connect(target) as remote:
        new_key = remote.seen_host_key and not target.host_key
        remember_host_key(target, remote)
        files = remote.list()
        probe = ".netmap-prova"
        remote.upload(io.BytesIO(b"prova di scrittura di NetMap\n"), probe)
        remote.delete(probe)
    db.commit()
    return {
        "ok": True,
        "backups": sum(1 for f in files if BACKUP_NAME.fullmatch(f.name)),
        "host_key": host_key_fingerprint(target.host_key),
        "host_key_new": bool(new_key),
    }


def remote_listing(db: Session, target: BackupTarget) -> list[dict]:
    with connect(target) as remote:
        remember_host_key(target, remote)
        files = remote.list()
    db.commit()
    out = [{"file": f.name, "size": f.size, "date": (name_date(f.name) or f.date),
            "kind": "key" if KEY_FILE.fullmatch(f.name) else "backup"}
           for f in files if BACKUP_NAME.fullmatch(f.name) or KEY_FILE.fullmatch(f.name)]
    return sorted(out, key=lambda f: (f["kind"] != "backup", -(f["date"].timestamp() if f["date"] else 0)))


def _fail(db: Session, target: BackupTarget, message: str) -> None:
    db.rollback()
    target = db.get(BackupTarget, target.id)
    if target is not None:
        target.last_error = message
        target.last_error_at = _now()
        db.commit()


def run_task(db: Session, task: BackupTask) -> None:
    target = db.get(BackupTarget, task.target_id)
    task.status = "running"
    db.commit()
    try:
        if task.action == "sync":
            task.message = sync(db, target)
        elif task.action == "fetch":
            task.message = f"Riportato sul server come {fetch(db, target, task.file or '')}"
        else:
            raise OffsiteError(f"Richiesta sconosciuta: {task.action}")
        task.status = "done"
    except OffsiteError as exc:
        logger.warning("%s su %s non riuscito: %s", task.action, target.name, exc)
        if task.action == "sync":
            _fail(db, target, str(exc))
        task = db.get(BackupTask, task.id)
        task.status, task.message = "error", str(exc)
    task.finished_at = _now()
    db.commit()


def recover_interrupted(db: Session) -> None:
    for task in db.scalars(select(BackupTask).where(BackupTask.status == "running")):
        task.status, task.message, task.finished_at = "error", "Interrotta da un riavvio del worker", _now()
    # Le richieste vecchie non servono più a nessuno
    old = _now() - timedelta(days=7)
    for task in db.scalars(select(BackupTask).where(BackupTask.created_at < old)):
        db.delete(task)
    db.commit()


def offsite_loop(session_factory) -> None:
    """Thread del worker: richieste dall'interfaccia ogni pochi secondi, file nuovi da copiare ogni minuto."""
    retry_at: dict[int, float] = {}
    next_scan = 0.0
    recovered = False
    while True:
        try:
            with session_factory() as db:
                if not recovered:
                    recover_interrupted(db)
                    recovered = True
                task = db.scalar(select(BackupTask).where(BackupTask.status == "queued").order_by(BackupTask.id).limit(1))
                if task is not None:
                    run_task(db, task)
                    retry_at.pop(task.target_id, None)
                    continue
                if time.monotonic() >= next_scan:
                    next_scan = time.monotonic() + SCAN_SECONDS
                    for target in db.scalars(select(BackupTarget).where(BackupTarget.enabled.is_(True))).all():
                        if retry_at.get(target.id, 0) > time.monotonic() or not pending(db, target):
                            continue
                        try:
                            logger.info("Copia su %s: %s", target.name, sync(db, target))
                            retry_at.pop(target.id, None)
                        except OffsiteError as exc:
                            logger.warning("Copia su %s non riuscita: %s", target.name, exc)
                            _fail(db, target, str(exc))
                            retry_at[target.id] = time.monotonic() + RETRY_MINUTES * 60
        except (OperationalError, ProgrammingError):
            time.sleep(30)  # database non pronto o migration non ancora applicata
            continue
        except Exception:
            logger.exception("Errore inatteso nelle copie dei backup")
        time.sleep(POLL_SECONDS)
