"""#42: file types by content, storage limits per account, safe file responses and the optional virus scan."""

import asyncio
import io
import os
import socket
import threading
import uuid
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from app.config import get_settings
from app.database import SessionLocal
from app.models import Document, User
from app.services.record_store import SqlRecordStore
from app.services.storage import sniff_content_type
from tests.conftest import HEIC_BYTES, PDF_BYTES, PNG_BYTES, WEBP_BYTES

MB = 1024 * 1024


def upload(client, record_id, *files):
    return client.post(f"/api/records/{record_id}/documents", files=[("files", f) for f in files])


def _user_id(email: str = "owner@example.com") -> str:
    with SessionLocal() as db:
        return db.query(User).filter_by(email=email).one().id


def _set_quota(user_id: str, quota: int | None) -> None:
    with SessionLocal() as db:
        db.get(User, user_id).quota_bytes = quota
        db.commit()


def _stored_files() -> list[Path]:
    return [p for p in get_settings().files_path.rglob("*") if p.is_file()]


# ---------------------------------------------------------------- file types


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (HEIC_BYTES, "image/heic"),
        (b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00mif1heic" + b"\x00" * 8, "image/heic"),
        (b"\x00\x00\x00\x18ftypavif\x00\x00\x00\x00mif1miaf" + b"\x00" * 8, None),  # AVIF
        (b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00mif1avif" + b"\x00" * 8, None),  # AVIF in a generic box
        (b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00isommp41" + b"\x00" * 8, None),  # MP4 video
    ],
)
def test_heic_is_recognised_from_its_content(head, expected):
    assert sniff_content_type(head) == expected


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("scan.webp", WEBP_BYTES),
        ("drawing.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
        ("report.pdf", b"<!doctype html><script>alert(1)</script>"),  # HTML dressed up as a PDF
        ("photo.png", b"<svg onload=alert(1)>"),  # SVG dressed up as a PNG
        ("page.html", b"<html></html>"),
    ],
)
def test_only_pdf_jpeg_png_heic_are_accepted(client, make_record, name, content):
    record = make_record()
    response = upload(client, record["id"], (name, content, "image/png"))
    assert response.status_code == 415
    assert "PDF, JPG, PNG, HEIC" in response.json()["detail"]
    assert _stored_files() == []


def test_existing_webp_files_are_still_served(client, make_record):
    record = make_record()
    user_id = _user_id()
    stored_name = f"{uuid.uuid4()}.webp"
    folder = get_settings().files_path / user_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / stored_name).write_bytes(WEBP_BYTES)
    with SessionLocal() as db:
        document = Document(record_id=record["id"], original_filename="old.webp", stored_filename=stored_name,
                            content_type="image/webp", size_bytes=len(WEBP_BYTES))
        db.add(document)
        db.commit()
        document_id = document.id
    response = client.get(f"/api/documents/{document_id}/view")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"


def test_config_lists_the_accepted_extensions(client):
    assert client.get("/api/config").json()["allowed_extensions"] == [".heic", ".heif", ".jpeg", ".jpg", ".pdf", ".png"]


@pytest.mark.parametrize("kind", ["view", "download"])
def test_file_responses_cannot_be_rendered_as_pages(client, make_record, kind):
    record = make_record()
    document = upload(client, record["id"], ("a.png", PNG_BYTES, "image/png")).json()[0]
    response = client.get(f"/api/documents/{document['id']}/{kind}")
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-security-policy"] == "default-src 'none'; sandbox"
    disposition = "inline" if kind == "view" else "attachment"
    assert response.headers["content-disposition"].startswith(f'{disposition}; filename="a.png"')


# ---------------------------------------------------------------- storage limits


def test_storage_use_and_default_limit(client, make_record):
    assert client.get("/api/storage").json() == {"used_bytes": 0, "quota_bytes": 100 * MB}
    record = make_record()
    upload(client, record["id"], ("a.pdf", PDF_BYTES, "application/pdf"))
    assert client.get("/api/storage").json()["used_bytes"] == len(PDF_BYTES)


def test_upload_beyond_the_limit_is_refused_and_nothing_is_kept(client, make_record):
    record = make_record()
    _set_quota(_user_id(), len(PDF_BYTES) + 10)
    assert upload(client, record["id"], ("a.pdf", PDF_BYTES, "application/pdf")).status_code == 201

    response = upload(client, record["id"], ("b.pdf", PDF_BYTES, "application/pdf"))
    assert response.status_code == 413
    assert response.json()["detail"].startswith("Not enough storage left for 'b.pdf': 0 KB free of ")
    assert len(_stored_files()) == 1


def test_a_batch_that_does_not_fit_is_refused_whole(client, make_record):
    record = make_record()
    _set_quota(_user_id(), len(PDF_BYTES) + len(PNG_BYTES) - 1)
    response = upload(client, record["id"], ("a.pdf", PDF_BYTES, "application/pdf"), ("b.png", PNG_BYTES, "image/png"))
    assert response.status_code == 413
    assert "'b.png'" in response.json()["detail"]
    assert _stored_files() == []
    assert client.get("/api/storage").json()["used_bytes"] == 0


def test_a_big_file_is_stopped_while_streaming(client, make_record):
    record = make_record()
    _set_quota(_user_id(), 2 * MB)
    big = b"%PDF-1.4\n" + os.urandom(5 * MB)
    response = upload(client, record["id"], ("big.pdf", big, "application/pdf"))
    assert response.status_code == 413
    assert _stored_files() == []


def test_two_uploads_at_once_cannot_both_squeeze_in(client, make_record):
    """The per-account upload lock: with room for one file, exactly one of two simultaneous uploads succeeds."""
    record = make_record()
    user_id = _user_id()
    _set_quota(user_id, len(PDF_BYTES) + 10)

    async def one_upload(name: str):
        with SessionLocal() as db:
            store = SqlRecordStore(db, user_id)
            try:
                await store.add_documents(store.get(record["id"]), [UploadFile(io.BytesIO(PDF_BYTES), filename=name)])
                return "saved"
            except Exception as error:  # noqa: BLE001
                return getattr(error, "status_code", type(error).__name__)

    async def both():
        return await asyncio.gather(one_upload("a.pdf"), one_upload("b.pdf"))

    assert sorted(asyncio.run(both()), key=str) == [413, "saved"]
    assert len(_stored_files()) == 1


def test_admin_changes_a_limit_and_lowering_it_deletes_nothing(client, second_client):
    record = second_client.post("/api/records", json={"record_type": "doctor_visit", "record_date": "2026-01-01"}).json()
    upload(second_client, record["id"], ("a.pdf", PDF_BYTES, "application/pdf"))
    user_id = _user_id("second@example.com")

    def account():
        return next(u for u in client.get("/api/admin/users").json() if u["email"] == "second@example.com")

    assert (account()["quota_bytes"], account()["quota_is_default"]) == (100 * MB, True)
    assert client.put(f"/api/admin/users/{user_id}/quota", json={"quota_mb": 1}).status_code == 204
    assert (account()["quota_bytes"], account()["quota_is_default"]) == (1 * MB, False)
    assert second_client.get("/api/storage").json()["quota_bytes"] == 1 * MB

    _set_quota(user_id, 1)  # lower than what is already stored
    assert second_client.get("/api/storage").json()["used_bytes"] == len(PDF_BYTES)
    assert upload(second_client, record["id"], ("b.pdf", PDF_BYTES, "application/pdf")).status_code == 413
    assert len(second_client.get(f"/api/records/{record['id']}").json()["documents"]) == 1

    assert client.put(f"/api/admin/users/{user_id}/quota", json={"quota_mb": None}).status_code == 204
    assert account()["quota_is_default"] is True
    assert client.put(f"/api/admin/users/{user_id}/quota", json={"quota_mb": 0}).status_code == 422
    assert client.put("/api/admin/users/nope/quota", json={"quota_mb": 5}).status_code == 404


# ---------------------------------------------------------------- virus scan (fake clamd)


class FakeClamd:
    """Answers clamd's INSTREAM like the real one: OK, FOUND (if the file holds EICAR), or nothing at all."""

    def __init__(self, path: Path, mode: str = "scan") -> None:
        self.path = str(path)
        self.mode = mode
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen()
        self.scanned = 0
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self) -> None:
        while True:
            try:
                connection, _ = self.server.accept()
            except OSError:
                return
            with connection:
                if self.mode == "silent":
                    continue
                data = b""
                while not data.endswith(b"\0\0\0\0"):
                    data += connection.recv(65536)
                self.scanned += 1
                found = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data
                connection.sendall(b"stream: Eicar-Signature FOUND\0" if found else b"stream: OK\0")

    def close(self) -> None:
        self.server.close()


@pytest.fixture
def clamd(tmp_path, monkeypatch):
    servers = []

    def start(mode: str = "scan") -> FakeClamd:
        server = FakeClamd(Path("/tmp") / f"clamd-test-{uuid.uuid4().hex[:8]}.ctl", mode)
        servers.append(server)
        monkeypatch.setattr(get_settings(), "clamav_socket", server.path)
        return server

    yield start
    for server in servers:
        server.close()
        Path(server.path).unlink(missing_ok=True)


def test_clean_files_pass_the_virus_scan(client, make_record, clamd):
    server = clamd()
    record = make_record()
    assert upload(client, record["id"], ("a.pdf", PDF_BYTES, "application/pdf")).status_code == 201
    assert server.scanned == 1


def test_infected_files_are_refused(client, make_record, clamd):
    clamd()
    record = make_record()
    infected = b"%PDF-1.4\nX5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*\n"
    response = upload(client, record["id"], ("bad.pdf", infected, "application/pdf"))
    assert response.status_code == 422
    assert response.json()["detail"] == "'bad.pdf' was refused by the virus scanner."
    assert _stored_files() == []


def test_upload_is_refused_when_the_scanner_does_not_answer(client, make_record, clamd, monkeypatch):
    monkeypatch.setattr("app.services.virus_scan.TIMEOUT_SECONDS", 0.5)
    clamd("silent")
    record = make_record()
    response = upload(client, record["id"], ("a.pdf", PDF_BYTES, "application/pdf"))
    assert response.status_code == 503
    assert _stored_files() == []


def test_upload_is_refused_when_the_scanner_is_missing(client, make_record, monkeypatch):
    monkeypatch.setattr(get_settings(), "clamav_socket", "/tmp/no-such-clamd.ctl")
    record = make_record()
    assert upload(client, record["id"], ("a.pdf", PDF_BYTES, "application/pdf")).status_code == 503
    assert _stored_files() == []
