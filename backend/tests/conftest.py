"""Test setup: an isolated temp database and files folder, and helpers for authenticated clients."""

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

# Settings must be in the environment before the application is imported.
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="medical-records-tests-"))
os.environ.update(
    {
        "GOOGLE_CLIENT_ID": "test-client-id",
        "GOOGLE_CLIENT_SECRET": "test-client-secret",
        "GOOGLE_REDIRECT_URI": "http://localhost:8000/api/auth/callback",
        "ALLOWED_EMAIL": "owner@example.com",
        "SESSION_SECRET": "test-secret-test-secret-test-secret-1234",
        "DATABASE_URL": f"sqlite:///{_TEST_ROOT / 'test.db'}",
        "FILES_DIR": str(_TEST_ROOT / "files"),
        "UPLOAD_DIR": str(_TEST_ROOT / "uploads"),
        "MAX_UPLOAD_SIZE_MB": "20",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.services import sessions  # noqa: E402

CSRF_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
WEBP_BYTES = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"


@pytest.fixture(scope="session", autouse=True)
def _lifespan() -> Iterator[None]:
    """Run the app's startup (migrations) once for the whole test session."""
    with TestClient(app):
        yield
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    yield
    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
    for folder in (get_settings().files_path, get_settings().upload_path):
        if folder.is_dir():
            for item in folder.iterdir():
                shutil.rmtree(item) if item.is_dir() else item.unlink()


@pytest.fixture
def anon() -> TestClient:
    """A client that is not logged in."""
    return TestClient(app, headers=CSRF_HEADERS)


def make_session_token(email: str = "owner@example.com") -> str:
    with SessionLocal() as db:
        user = sessions.get_or_create_user(db, email, "Owner")
        return sessions.create_session(db, user)


@pytest.fixture
def client() -> TestClient:
    """A client logged in as the allowed user (sends the CSRF header like the web app does)."""
    test_client = TestClient(app, headers=CSRF_HEADERS)
    test_client.cookies.set("session", make_session_token())
    return test_client


def record_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {"record_type": "doctor_visit", "record_date": "2026-09-05"}
    payload.update(overrides)
    return payload


@pytest.fixture
def make_record(client: TestClient):
    def _make(**overrides: object) -> dict:
        response = client.post("/api/records", json=record_payload(**overrides))
        assert response.status_code == 201, response.text
        return response.json()

    return _make
