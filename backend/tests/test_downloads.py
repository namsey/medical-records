"""sec-1: downloads of a user's data are rate-limited, audited, built two at a time, and on the data disk."""

import os
import stat

import pytest

from app.config import get_settings
from app.database import SessionLocal
from app.models import AuditEvent, User
from app.services import backup
from app.services.accounts import build_data_export
from app.services.storage import get_file_store
from tests.conftest import PDF_BYTES


def _owner_id() -> str:
    with SessionLocal() as db:
        return db.query(User).filter_by(email="owner@example.com").one().id


def _downloads() -> list[tuple[str, str | None]]:
    with SessionLocal() as db:
        return [(e.actor_email, e.detail) for e in db.query(AuditEvent).filter_by(action="data_downloaded").order_by(AuditEvent.at)]


def test_the_sixth_backup_within_an_hour_is_refused(client):
    for _ in range(5):
        assert client.get("/api/backup").status_code == 200
    response = client.get("/api/backup")
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert response.json()["detail"].startswith("You downloaded your data several times in the last hour.")


def test_all_data_downloads_share_one_budget(client):
    assert client.get("/api/backup").status_code == 200
    assert client.get("/api/export/json").status_code == 200
    assert client.get("/api/account/export").status_code == 200
    assert client.get("/api/export/json").status_code == 200
    assert client.get("/api/backup").status_code == 200
    for path in ("/api/backup", "/api/export/json", "/api/account/export"):
        assert client.get(path).status_code == 429, path


def test_each_download_is_audited(client):
    client.get("/api/backup")
    client.get("/api/export/json")
    assert _downloads() == [("owner@example.com", "backup"), ("owner@example.com", "json")]


@pytest.mark.parametrize("path", ["/api/backup", "/api/account/export"])
def test_busy_when_two_archives_are_already_being_built(client, monkeypatch, path):
    monkeypatch.setattr(backup, "ARCHIVE_WAIT_SECONDS", 0.1)
    assert backup.ARCHIVE_SLOTS.acquire(timeout=1) and backup.ARCHIVE_SLOTS.acquire(timeout=1)
    try:
        response = client.get(path)
        assert (response.status_code, response.json()) == (503, {"detail": "Busy, try again in a minute"})
    finally:
        backup.ARCHIVE_SLOTS.release()
        backup.ARCHIVE_SLOTS.release()
    assert client.get(path).status_code == 200  # free again


def test_archives_are_built_on_the_data_disk(client, make_record):
    record = make_record()
    client.post(f"/api/records/{record['id']}/documents", files={"files": ("a.pdf", PDF_BYTES, "application/pdf")})
    data_tmp = get_settings().sqlite_path.parent / "tmp"
    for archive in (
        backup.create_backup_zip(_owner_id()),
        build_data_export(SessionLocal(), _owner_id(), get_file_store()),
    ):
        try:
            assert archive.parent == data_tmp
        finally:
            archive.unlink()
    assert list(data_tmp.iterdir()) == []


def test_startup_empties_the_scratch_folder_and_keeps_it_private():
    folder = backup.scratch_dir()
    (folder / "left-over.zip").write_bytes(b"old")
    (folder / "medical-backup-db-old").mkdir()
    (folder / "medical-backup-db-old" / "medical_records.db").write_bytes(b"old copy")
    os.chmod(folder, 0o755)
    backup.prepare_scratch_dir()
    assert list(folder.iterdir()) == []
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
