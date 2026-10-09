"""Local-filesystem storage for uploaded documents.

Files are stored under UPLOAD_DIR/<folder>/<uuid>.<ext>. The original file name only lives in the database
(sanitised); the stored name is generated, so user input never becomes part of a filesystem path.
"""

import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, status
from starlette.datastructures import UploadFile

from app.config import get_settings
from app.models import Document, MedicalRecord

logger = logging.getLogger(__name__)

# content type -> canonical extension
ALLOWED_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

TYPE_FOLDERS: dict[str, str] = {
    "prescription": "prescriptions",
    "lab_report": "lab_reports",
    "medical_document": "medical_documents",
    "scan": "scans",
    "doctor_visit": "other",
    "diagnosis": "other",
    "other": "other",
}
ALL_FOLDERS = {"prescriptions", "lab_reports", "medical_documents", "scans", "other"}

_STORED_NAME_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|jpg|png|webp)$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
CHUNK_SIZE = 1024 * 1024


def ensure_storage_dirs() -> None:
    base = get_settings().upload_path
    for folder in ALL_FOLDERS:
        (base / folder).mkdir(parents=True, exist_ok=True)


def sniff_content_type(head: bytes) -> str | None:
    """Identify the real file type from its leading bytes (never trust the client's claim)."""
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def sanitize_filename(raw: str | None) -> str:
    """Reduce a client-supplied file name to a harmless display name."""
    name = (raw or "").replace("\\", "/").split("/")[-1]
    name = _CONTROL_CHARS_RE.sub("", name).strip().strip(".")
    if len(name) > 200:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 200 - len(ext) - 1] + dot + ext) if dot and len(ext) <= 10 else name[:200]
    return name or "document"


def folder_for(record_type: str) -> str:
    return TYPE_FOLDERS.get(record_type, "other")


def stored_path(document: Document) -> Path:
    """Absolute path of a document's file, guaranteed to be inside the upload directory."""
    base = get_settings().upload_path
    if document.storage_folder not in ALL_FOLDERS or not _STORED_NAME_RE.match(document.stored_filename):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    candidate = (base / document.storage_folder / document.stored_filename).resolve()
    if not candidate.is_relative_to(base):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return candidate


def remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove a stored file (%s)", path.name)


async def save_upload(upload: UploadFile, record: MedicalRecord) -> Document:
    """Validate and store one uploaded file; returns an unsaved Document row. Raises HTTPException."""
    settings = get_settings()
    max_bytes = settings.max_upload_bytes
    display_name = sanitize_filename(upload.filename)

    head = await upload.read(16)
    await upload.seek(0)
    content_type = sniff_content_type(head)
    if content_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"'{display_name}' is not a supported file. Allowed types: PDF, JPG, JPEG, PNG, WEBP.",
        )
    extension = Path(display_name).suffix.lower()
    if extension:
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"'{display_name}' has an unsupported file extension. Allowed: PDF, JPG, JPEG, PNG, WEBP.",
            )
        if ALLOWED_EXTENSIONS[extension] != content_type:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"'{display_name}' does not match its file extension.",
            )
    else:
        display_name = f"{display_name}{ALLOWED_TYPES[content_type]}"

    folder = folder_for(record.record_type)
    stored_name = f"{uuid.uuid4()}{ALLOWED_TYPES[content_type]}"
    destination = settings.upload_path / folder / stored_name
    destination.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    try:
        with open(destination, "xb") as out:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"'{display_name}' is larger than the {settings.max_upload_size_mb} MB limit.",
                    )
                out.write(chunk)
        if size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'{display_name}' is empty.")
        os.chmod(destination, 0o600)
    except BaseException:
        remove_file(destination)
        raise

    return Document(
        record_id=record.id,
        original_filename=display_name,
        stored_filename=stored_name,
        storage_folder=folder,
        content_type=content_type,
        size_bytes=size,
    )


def iter_stored_files(base: Path):
    """Yield (absolute_path, relative_posix_path) for every stored file."""
    for path in sorted(base.rglob("*")):
        if path.is_file():
            yield path, path.relative_to(base).as_posix()
