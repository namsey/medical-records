"""Moving files from the old UPLOAD_DIR/<type folder>/ layout to FILES_DIR/<user_id>/ at startup."""

import errno
import os
import uuid

from app.config import get_settings
from app.database import SessionLocal
from app.models import Document, User
from app.services import storage
from tests.conftest import PDF_BYTES, PNG_BYTES


def _legacy_document(record_id: str, folder: str, content: bytes | None) -> str:
    """A document row as an older version wrote it, with its file in the old folder (unless content is None)."""
    stored_name = f"{uuid.uuid4()}.pdf"
    if content is not None:
        path = get_settings().upload_path / folder / stored_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    with SessionLocal() as db:
        document = Document(
            record_id=record_id,
            original_filename="old.pdf",
            stored_filename=stored_name,
            storage_folder=folder,
            content_type="application/pdf",
            size_bytes=len(content or b""),
        )
        db.add(document)
        db.commit()
        return document.id


def _relocate() -> tuple[int, int]:
    with SessionLocal() as db:
        return storage.relocate_legacy_files(db, get_settings().upload_path, storage.get_file_store())


def _owner_id() -> str:
    with SessionLocal() as db:
        return db.query(User).filter_by(email="owner@example.com").one().id


def test_old_files_move_to_the_owners_folder(client, make_record):
    record = make_record()
    document_id = _legacy_document(record["id"], "scans", PDF_BYTES)
    legacy_file = next(get_settings().upload_path.rglob("*.pdf"))

    assert _relocate() == (1, 0)

    target = get_settings().files_path / _owner_id() / legacy_file.name
    assert target.read_bytes() == PDF_BYTES
    assert not legacy_file.exists()
    assert not get_settings().upload_path.exists()  # empty old folders are removed
    with SessionLocal() as db:
        assert db.get(Document, document_id).storage_folder == ""
    response = client.get(f"/api/documents/{document_id}/download")
    assert response.status_code == 200
    assert response.content == PDF_BYTES

    assert _relocate() == (0, 0)  # nothing left to do
    assert target.read_bytes() == PDF_BYTES


def test_missing_file_is_counted_and_left_marked(client, make_record):
    record = make_record()
    document_id = _legacy_document(record["id"], "other", None)
    assert _relocate() == (0, 1)
    assert _relocate() == (0, 1)
    with SessionLocal() as db:
        assert db.get(Document, document_id).storage_folder == "other"
    assert client.get(f"/api/documents/{document_id}/view").status_code == 404


def test_resumes_after_a_crash_between_move_and_commit(client, make_record):
    record = make_record()
    document_id = _legacy_document(record["id"], "lab_reports", PDF_BYTES)
    legacy_file = next(get_settings().upload_path.rglob("*.pdf"))
    target = get_settings().files_path / _owner_id() / legacy_file.name
    target.parent.mkdir(parents=True, exist_ok=True)
    os.rename(legacy_file, target)  # the file moved, but the row still says "lab_reports"

    assert _relocate() == (1, 0)
    assert target.read_bytes() == PDF_BYTES
    with SessionLocal() as db:
        assert db.get(Document, document_id).storage_folder == ""


def test_moves_across_disks_by_copying(client, make_record, monkeypatch):
    record = make_record()
    _legacy_document(record["id"], "scans", PNG_BYTES)
    legacy_file = next(get_settings().upload_path.rglob("*.pdf"))

    def cross_device(*_args):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(storage.os, "rename", cross_device)
    assert _relocate() == (1, 0)

    target = get_settings().files_path / _owner_id() / legacy_file.name
    assert target.read_bytes() == PNG_BYTES
    assert target.stat().st_mode & 0o777 == 0o600
    assert not legacy_file.exists()
    assert [p.name for p in target.parent.iterdir()] == [target.name]  # no partial copy left behind


def test_tampered_folder_is_not_followed(client, make_record):
    record = make_record()
    secret = get_settings().upload_path.parent / "secret.pdf"
    secret.write_bytes(PDF_BYTES)
    with SessionLocal() as db:
        db.add(
            Document(
                record_id=record["id"],
                original_filename="x.pdf",
                stored_filename="secret.pdf",
                storage_folder="..",
                content_type="application/pdf",
                size_bytes=1,
            )
        )
        db.commit()
    assert _relocate() == (0, 1)
    assert secret.read_bytes() == PDF_BYTES
    secret.unlink()
