import re
from pathlib import Path

import pytest

from app.config import get_settings
from app.database import SessionLocal
from app.models import Document, User
from tests.conftest import HEIC_BYTES, JPEG_BYTES, PDF_BYTES, PNG_BYTES


def upload(client, record_id, name, content, content_type="application/octet-stream"):
    return client.post(f"/api/records/{record_id}/documents", files={"files": (name, content, content_type)})


def stored_files() -> list[Path]:
    return [p for p in get_settings().files_path.rglob("*") if p.is_file()]


@pytest.mark.parametrize(
    ("name", "content", "mime", "ext"),
    [
        ("report.pdf", PDF_BYTES, "application/pdf", ".pdf"),
        ("photo.jpg", JPEG_BYTES, "image/jpeg", ".jpg"),
        ("photo.JPEG", JPEG_BYTES, "image/jpeg", ".jpg"),
        ("scan.png", PNG_BYTES, "image/png", ".png"),
        ("photo.heic", HEIC_BYTES, "image/heic", ".heic"),
        ("photo.HEIF", HEIC_BYTES, "image/heic", ".heic"),
    ],
)
def test_upload_allowed_types(client, make_record, name, content, mime, ext):
    record = make_record()
    response = upload(client, record["id"], name, content)
    assert response.status_code == 201, response.text
    document = response.json()[0]
    assert document["original_filename"] == name
    assert document["content_type"] == mime
    assert document["size_bytes"] == len(content)
    files = stored_files()
    assert len(files) == 1
    assert files[0].suffix == ext
    assert re.fullmatch(r"[0-9a-f-]{36}", files[0].stem)  # UUID name, original name not used
    assert name not in files[0].name


def test_files_are_stored_in_the_owners_folder(client, make_record):
    with SessionLocal() as db:
        owner_id = db.query(User).filter_by(email="owner@example.com").one().id
    for record_type in ("prescription", "scan", "doctor_visit"):
        record = make_record(record_type=record_type, title="T")
        assert upload(client, record["id"], "a.pdf", PDF_BYTES).status_code == 201
    files = stored_files()
    assert len(files) == 3
    assert {p.parent for p in files} == {get_settings().files_path / owner_id}
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in files)
    assert (get_settings().files_path / owner_id).stat().st_mode & 0o777 == 0o700


def test_upload_multiple_files_in_one_request(client, make_record):
    record = make_record()
    response = client.post(
        f"/api/records/{record['id']}/documents",
        files=[("files", ("a.pdf", PDF_BYTES, "application/pdf")), ("files", ("b.png", PNG_BYTES, "image/png"))],
    )
    assert response.status_code == 201
    assert len(response.json()) == 2
    assert len(client.get(f"/api/records/{record['id']}").json()["documents"]) == 2


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("notes.txt", b"just text"),
        ("malware.exe", b"MZ\x90\x00\x03"),
        ("script.pdf", b"<script>alert(1)</script>"),  # claims to be a PDF but is not
        ("page.html", b"<html></html>"),
        ("photo.png", JPEG_BYTES),  # extension disagrees with content
        ("doc.pdf", PNG_BYTES),
        ("empty.pdf", b""),
        ("image.gif", b"GIF89a....."),
    ],
)
def test_upload_rejects_bad_files(client, make_record, name, content):
    record = make_record()
    response = upload(client, record["id"], name, content, "application/pdf")
    assert response.status_code in (400, 415)
    assert stored_files() == []
    assert client.get(f"/api/records/{record['id']}").json()["documents"] == []


def test_client_supplied_content_type_is_ignored(client, make_record):
    record = make_record()
    response = upload(client, record["id"], "x.pdf", PDF_BYTES, "text/html")
    assert response.status_code == 201
    assert response.json()[0]["content_type"] == "application/pdf"


def test_file_without_extension_gets_one(client, make_record):
    record = make_record()
    response = upload(client, record["id"], "camera_image", JPEG_BYTES)
    assert response.status_code == 201
    assert response.json()[0]["original_filename"] == "camera_image.jpg"


def test_unsafe_original_filename_is_sanitised(client, make_record):
    record = make_record()
    response = upload(client, record["id"], "../../etc/passwd\x00.pdf", PDF_BYTES)
    assert response.status_code == 201
    assert "/" not in response.json()[0]["original_filename"]
    assert "\x00" not in response.json()[0]["original_filename"]
    for path in stored_files():
        assert path.resolve().is_relative_to(get_settings().files_path)


def test_batch_is_all_or_nothing(client, make_record):
    record = make_record()
    response = client.post(
        f"/api/records/{record['id']}/documents",
        files=[("files", ("a.pdf", PDF_BYTES, "application/pdf")), ("files", ("b.txt", b"nope", "text/plain"))],
    )
    assert response.status_code == 415
    assert stored_files() == []
    assert client.get(f"/api/records/{record['id']}").json()["documents"] == []


def test_upload_size_limit(client, make_record, monkeypatch):
    record = make_record()
    monkeypatch.setattr(get_settings(), "max_upload_size_mb", 1)
    big = PDF_BYTES + b"0" * (1024 * 1024)
    response = upload(client, record["id"], "big.pdf", big)
    assert response.status_code == 413
    assert stored_files() == []
    ok = upload(client, record["id"], "small.pdf", PDF_BYTES)
    assert ok.status_code == 201


def test_oversized_request_rejected_before_reading_body(client, make_record):
    record = make_record()
    limit = get_settings().max_upload_bytes
    response = client.post(
        f"/api/records/{record['id']}/documents",
        content=b"x",
        headers={"Content-Length": str(limit + 5 * 1024 * 1024), "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 413


def test_upload_to_missing_record_is_404(client):
    assert upload(client, "missing", "a.pdf", PDF_BYTES).status_code == 404


def test_upload_without_files_is_400(client, make_record):
    record = make_record()
    response = client.post(f"/api/records/{record['id']}/documents", data={"x": "y"})
    assert response.status_code == 400


def test_view_serves_inline_and_download_as_attachment(client, make_record):
    record = make_record()
    document = upload(client, record["id"], "My Report.pdf", PDF_BYTES).json()[0]

    view = client.get(f"/api/documents/{document['id']}/view")
    assert view.status_code == 200
    assert view.content == PDF_BYTES
    assert view.headers["content-type"] == "application/pdf"
    assert view.headers["content-disposition"].startswith("inline")
    assert "My%20Report.pdf" in view.headers["content-disposition"]
    assert view.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in view.headers["cache-control"]

    download = client.get(f"/api/documents/{document['id']}/download")
    assert download.status_code == 200
    assert download.content == PDF_BYTES
    assert download.headers["content-disposition"].startswith("attachment")

    image = upload(client, record["id"], "p.png", PNG_BYTES).json()[0]
    assert client.get(f"/api/documents/{image['id']}/view").headers["content-type"] == "image/png"


def test_files_are_not_served_without_login(client, anon, make_record):
    record = make_record()
    document = upload(client, record["id"], "a.pdf", PDF_BYTES).json()[0]
    stored = stored_files()[0]
    assert anon.get(f"/api/documents/{document['id']}/view").status_code == 401
    assert anon.get(f"/api/documents/{document['id']}/download").status_code == 401
    # The upload folder is not exposed as a static path either.
    for path in (f"/files/{stored.parent.name}/{stored.name}", f"/data/files/{stored.parent.name}/{stored.name}",
                 f"/{stored.parent.name}/{stored.name}", f"/{stored.name}"):
        response = anon.get(path)
        assert PDF_BYTES not in response.content


def test_unknown_document_is_404(client):
    assert client.get("/api/documents/nope/view").status_code == 404
    assert client.get("/api/documents/nope").status_code == 404
    assert client.delete("/api/documents/nope").status_code == 404


def test_tampered_database_row_cannot_escape_upload_dir(client, make_record):
    record = make_record()
    document = upload(client, record["id"], "a.pdf", PDF_BYTES).json()[0]
    secret = get_settings().files_path.parent / "secret.txt"
    secret.write_text("top secret")
    with SessionLocal() as db:
        row = db.get(Document, document["id"])
        row.stored_filename = "../../secret.txt"
        db.commit()
    assert client.get(f"/api/documents/{document['id']}/view").status_code == 404
    with SessionLocal() as db:
        row = db.get(Document, document["id"])
        row.stored_filename = "00000000-0000-0000-0000-000000000000.pdf"
        row.storage_folder = "../"
        db.commit()
    assert client.get(f"/api/documents/{document['id']}/view").status_code == 404
    secret.unlink()


def test_missing_file_on_disk_is_404(client, make_record):
    record = make_record()
    document = upload(client, record["id"], "a.pdf", PDF_BYTES).json()[0]
    stored_files()[0].unlink()
    assert client.get(f"/api/documents/{document['id']}/view").status_code == 404


def test_delete_document_removes_file(client, make_record):
    record = make_record()
    document = upload(client, record["id"], "a.pdf", PDF_BYTES).json()[0]
    assert len(stored_files()) == 1
    assert client.delete(f"/api/documents/{document['id']}").status_code == 204
    assert stored_files() == []
    assert client.get(f"/api/documents/{document['id']}/view").status_code == 404
    assert client.get(f"/api/records/{record['id']}").json()["documents"] == []


def test_deleting_record_removes_its_files(client, make_record):
    record = make_record()
    upload(client, record["id"], "a.pdf", PDF_BYTES)
    upload(client, record["id"], "b.png", PNG_BYTES)
    assert len(stored_files()) == 2
    assert client.delete(f"/api/records/{record['id']}").status_code == 204
    assert stored_files() == []


def test_record_list_shows_attachment_count(client, make_record):
    record = make_record()
    upload(client, record["id"], "a.pdf", PDF_BYTES)
    item = client.get("/api/records").json()["items"][0]
    assert item["document_count"] == 1
