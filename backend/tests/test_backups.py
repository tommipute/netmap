"""Backup: copie fuori dal server (con una destinazione finta su cartella), carica/scarica, ripristino, chiave."""
import json
import os
import time
from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import settings
from app.core.secrets import decrypt, encrypt, master_key
from app.models import BackupCopy, BackupTarget, BackupTask, SnmpProfile
from app.services import keys, offsite

SMB = {"name": "NAS", "type": "smb", "host": "nas.azienda.local", "share": "backup", "folder": "netmap",
       "username": "AZIENDA\\backup", "password": "segreta", "keep_days": 30}


class FolderRemote(offsite.Remote):
    """Destinazione finta: una cartella locale al posto del NAS o del server SFTP."""

    def __init__(self, path):
        self.path = path
        path.mkdir(exist_ok=True)

    def list(self):
        return [offsite.RemoteFile(p.name, p.stat().st_size, datetime.fromtimestamp(p.stat().st_mtime))
                for p in self.path.iterdir() if p.is_file()]

    def upload(self, source, name):
        with offsite._open_source(source) as src:
            (self.path / name).write_bytes(src.read())

    def download(self, name, target):
        target.write((self.path / name).read_bytes())

    def delete(self, name):
        (self.path / name).unlink()


@pytest.fixture()
def folders(tmp_path, monkeypatch):
    local, remote = tmp_path / "backups", tmp_path / "remote"
    local.mkdir()
    monkeypatch.setattr(settings, "backup_dir", str(local))
    monkeypatch.setattr(offsite, "connect", lambda target: FolderRemote(remote))
    return local, remote


@pytest.fixture()
def updater_dir(tmp_path, monkeypatch):
    path = tmp_path / "updater"
    path.mkdir()
    monkeypatch.setattr(settings, "updater_dir", str(path))
    return path


def stamp(when: datetime) -> str:
    return when.strftime("%Y%m%d-%H%M%S")


def dump(folder, name, age_seconds=3600, size=100):
    path = folder / name
    path.write_bytes(offsite.DUMP_MAGIC + b"x" * size)
    moment = time.time() - age_seconds
    os.utime(path, (moment, moment))
    return path


def test_destinazioni_validazione_e_segreti(client, session_factory, anonymous):
    assert client.post("/api/backup-targets", json={**SMB, "share": ""}).status_code == 422
    assert client.post("/api/backup-targets", json={**SMB, "password": None}).status_code == 422
    assert client.post("/api/backup-targets", json={**SMB, "host": "\\\\nas\\backup"}).status_code == 422
    assert client.post("/api/backup-targets", json={**SMB, "folder": "a/../b"}).status_code == 422

    response = client.post("/api/backup-targets", json=SMB)
    assert response.status_code == 201, response.text
    target = response.json()
    assert target["has_secret"] is True and "password" not in target and "secret_enc" not in target
    with session_factory() as db:
        row = db.get(BackupTarget, target["id"])
        assert decrypt(row.secret_enc) == "segreta"
        row.host_key = "ssh-ed25519 AAAA"
        db.commit()

    # Cambiando server la chiave registrata si dimentica (SFTP)
    assert client.patch(f"/api/backup-targets/{target['id']}", json={"description": "nota"}).json()["host_key"] == "ssh-ed25519 AAAA"
    assert client.patch(f"/api/backup-targets/{target['id']}", json={"host": "nas2"}).json()["host_key"] is None
    with session_factory() as db:
        db.get(BackupTarget, target["id"]).host_key = "ssh-ed25519 BBBB"
        db.commit()
    assert client.patch(f"/api/backup-targets/{target['id']}", json={"forget_host_key": True}).json()["host_key"] is None

    sftp = {"name": "SFTP", "type": "sftp", "host": "backup.example.com", "username": "netmap"}
    assert "password o la chiave" in client.post("/api/backup-targets", json=sftp).json()["detail"]
    bad_key = client.post("/api/backup-targets", json={**sftp, "private_key": "non è una chiave"})
    assert bad_key.status_code == 422 and "chiave privata" in bad_key.json()["detail"]
    assert client.post("/api/backup-targets", json={**sftp, "password": "x"}).status_code == 201

    assert anonymous.get("/api/backup-targets").status_code == 401
    assert anonymous.get("/api/backups").status_code == 401

    # Nello storico: chi l'ha cambiata e il server, mai la password
    history = client.get("/api/audit-log", params={"object_type": "backup_target"}).json()
    text = json.dumps(history)
    assert "nas2" in text and "segreta" not in text


def test_copia_fuori_dal_server(client, session_factory, folders):
    local, remote = folders
    target_id = client.post("/api/backup-targets", json={**SMB, "include_key": True}).json()["id"]
    now = datetime.now()
    recent = [dump(local, f"daily-{stamp(now - timedelta(hours=1))}.dump"),
              dump(local, f"netmap-{stamp(now - timedelta(hours=2))}-abc1234.dump")]
    dump(local, "imported-daily-20200101-023000.dump")  # caricato qui: non si ricopia
    dump(local, f"daily-{stamp(now - timedelta(days=60))}.dump", age_seconds=60 * 86400)  # verrebbe subito cancellato
    dump(local, f"manual-{stamp(now)}.dump", age_seconds=2)  # forse ancora in scrittura

    with session_factory() as db:
        target = db.get(BackupTarget, target_id)
        assert sorted(p.name for p in offsite.pending(db, target)) == sorted(p.name for p in recent)
        assert offsite.sync(db, target) == "2 file copiati"
        assert db.get(BackupTarget, target_id).last_copy_at is not None
    names = {p.name for p in remote.iterdir()}
    assert names == {p.name for p in recent} | {offsite.key_file_name()}
    assert (remote / offsite.key_file_name()).read_text().strip() == master_key()

    # Sulla destinazione: un notturno vecchio (si cancella) e un file di qualcun altro (resta)
    old_remote = f"daily-{stamp(now - timedelta(days=45))}.dump"
    (remote / old_remote).write_bytes(b"PGDMPvecchio")
    (remote / "altro.txt").write_text("non mio")
    with session_factory() as db:
        assert offsite.sync(db, db.get(BackupTarget, target_id)) == "0 file copiati, 1 vecchio cancellato"
    assert not (remote / old_remote).exists() and (remote / "altro.txt").exists()

    overview = client.get("/api/backups").json()
    assert overview["mounted"] is True
    assert overview["copies"][recent[0].name] == [target_id]

    # Prova, elenco, "copia ora" e "riporta sul server" (le richieste le esegue il worker)
    assert client.post(f"/api/backup-targets/{target_id}/test").json()["backups"] == 2
    listing = client.get(f"/api/backup-targets/{target_id}/files").json()
    assert [f["kind"] for f in listing] == ["backup", "backup", "key"]
    assert client.post(f"/api/backup-targets/{target_id}/sync").status_code == 202
    response = client.post(f"/api/backup-targets/{target_id}/fetch", json={"file": recent[1].name})
    assert response.status_code == 202
    with session_factory() as db:
        for task in db.scalars(select(BackupTask).order_by(BackupTask.id)).all():
            offsite.run_task(db, task)
    tasks = client.get("/api/backups").json()["tasks"]
    assert [t["status"] for t in tasks] == ["done", "done"], tasks
    assert tasks[0]["message"] == f"Riportato sul server come imported-{recent[1].name}"
    fetched = local / f"imported-{recent[1].name}"
    assert fetched.read_bytes() == recent[1].read_bytes() and oct(fetched.stat().st_mode)[-3:] == "644"

    # Una seconda volta no: il file c'è già
    client.post(f"/api/backup-targets/{target_id}/fetch", json={"file": recent[1].name})
    with session_factory() as db:
        task = db.scalar(select(BackupTask).where(BackupTask.status == "queued"))
        offsite.run_task(db, task)
        assert task.status == "error" and "c'è già" in task.message

    # Destinazione che non risponde: errore sulla destinazione
    def broken(target):
        raise offsite.OffsiteError("Il server nas.azienda.local non risponde sulla porta 445")

    offsite_connect = offsite.connect
    offsite.connect = broken
    try:
        client.post(f"/api/backup-targets/{target_id}/sync")
        with session_factory() as db:
            offsite.run_task(db, db.scalar(select(BackupTask).where(BackupTask.status == "queued")))
        target = client.get(f"/api/backup-targets/{target_id}").json()
        assert "non risponde" in target["last_error"]
        assert client.post(f"/api/backup-targets/{target_id}/test").status_code == 502
    finally:
        offsite.connect = offsite_connect


def test_carica_scarica_e_ripristina(client, folders, updater_dir):
    local, _ = folders
    content = offsite.DUMP_MAGIC + b"dati del vecchio server"
    response = client.put("/api/backups/upload", params={"name": "C:\\backup\\vecchio.dump"}, content=content)
    assert response.status_code == 201, response.text
    assert response.json() == {"file": "imported-vecchio.dump"}
    assert (local / "imported-vecchio.dump").read_bytes() == content
    assert client.put("/api/backups/upload", params={"name": "vecchio.dump"}, content=content).status_code == 409

    wrong = client.put("/api/backups/upload", params={"name": "foto.dump"}, content=b"\x89PNG...")
    assert wrong.status_code == 422 and "non è un backup" in wrong.json()["detail"]
    assert client.put("/api/backups/upload", params={"name": "foto.png"}, content=content).status_code == 422
    assert sorted(p.name for p in local.iterdir()) == ["imported-vecchio.dump"]  # niente file a metà

    download = client.get("/api/backups/files/imported-vecchio.dump")
    assert download.status_code == 200 and download.content == content
    assert client.get("/api/backups/files/..%2Fsegreto.dump").status_code in (404, 422)
    assert client.get("/api/backups/files/manca.dump").status_code == 404

    assert client.post("/api/backups/restore", json={"file": "manca.dump"}).status_code == 404
    response = client.post("/api/backups/restore", json={"file": "imported-vecchio.dump"})
    assert response.status_code == 202
    request = json.loads((updater_dir / "request.json").read_text())
    assert request["action"] == "restore" and request["file"] == "imported-vecchio.dump"
    assert request["requested_by"] == "admin"
    # Un controllo chiesto dopo non prende il posto del ripristino
    client.post("/api/updates/request", json={"action": "check"})
    assert json.loads((updater_dir / "request.json").read_text())["action"] == "restore"


def test_chiave_dei_segreti(client, session_factory, folders):
    _, remote = folders
    old_key = Fernet.generate_key().decode()
    with session_factory() as db:
        db.add(SnmpProfile(name="nuovo", version="v2c", community_enc=encrypt("pubblica")))
        db.add(SnmpProfile(name="dal backup", version="v2c", community_enc=Fernet(old_key.encode()).encrypt(b"vecchia").decode()))
        db.commit()
    secrets = client.get("/api/backups").json()["secrets"]
    assert secrets == {"fingerprint": keys.fingerprint(), "total": 2, "unreadable": 1}

    assert client.post("/api/backups/secrets-key/rekey", json={"key": "nonvalida"}).status_code == 422
    other = client.post("/api/backups/secrets-key/rekey", json={"key": Fernet.generate_key().decode()}).json()
    assert other == {"fixed": 0, "unreadable": 1}

    # La chiave del vecchio server copiata sulla destinazione dei backup
    target_id = client.post("/api/backup-targets", json=SMB).json()["id"]
    remote.mkdir(exist_ok=True)
    key_name = f"netmap-secrets-{keys.fingerprint(old_key)}.key"
    (remote / key_name).write_text(old_key + "\n")
    assert client.post(f"/api/backup-targets/{target_id}/use-key", json={"file": "altro.dump"}).status_code == 502
    assert client.post(f"/api/backup-targets/{target_id}/use-key", json={"file": key_name}).json() == {"fixed": 1, "unreadable": 0}
    with session_factory() as db:
        profile = db.scalar(select(SnmpProfile).where(SnmpProfile.name == "dal backup"))
        assert decrypt(profile.community_enc) == "vecchia"
    assert client.get("/api/backups").json()["secrets"]["unreadable"] == 0

    response = client.get("/api/backups/secrets-key")
    assert response.text.strip() == master_key()
    assert f"netmap-secrets-{keys.fingerprint()}.key" in response.headers["content-disposition"]


def test_nomi_dei_backup():
    assert offsite.COPIED.fullmatch("daily-20261009-023000.dump")
    assert offsite.COPIED.fullmatch("netmap-20261009-023000-abc1234.dump")
    assert offsite.COPIED.fullmatch("before-restore-20261009-023000.dump")
    assert not offsite.COPIED.fullmatch("imported-daily-20261009-023000.dump")
    assert not offsite.BACKUP_NAME.fullmatch("../x.dump")
    assert offsite.name_date("before-restore-20261009-023000.dump") == datetime(2026, 10, 9, 2, 30)
    assert offsite.host_key_fingerprint("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl") \
        .startswith("SHA256:")
    assert BackupCopy.__tablename__ == "backup_copies"
