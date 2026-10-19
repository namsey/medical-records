"""FileStore: where uploaded documents live on disk.

Files are stored as FILES_DIR/<user_id>/<uuid>.<ext>. The original file name only lives in the database
(sanitised); the stored name is generated, so user input never becomes part of a filesystem path.

Older versions stored files as UPLOAD_DIR/<type folder>/<uuid>.<ext>; `relocate_legacy_files` moves them
into the per-user layout at startup.
"""

import errno
import logging
import os
import re
import shutil
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
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

# Type folders of the old UPLOAD_DIR layout, only read when moving files to the per-user layout.
LEGACY_FOLDERS = {"prescriptions", "lab_reports", "medical_documents", "scans", "other"}

_STORED_NAME_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|jpg|png|webp)$")
_USER_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
CHUNK_SIZE = 1024 * 1024


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


def remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove a stored file (%s)", path.name)


async def _validated_type(upload: UploadFile, display_name: str) -> tuple[str, str]:
    """The real content type (from the file's first bytes) and the display name, with an extension added if needed."""
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
        return content_type, display_name
    return content_type, f"{display_name}{ALLOWED_TYPES[content_type]}"


@dataclass
class StoredFile:
    stored_name: str
    display_name: str
    content_type: str
    size_bytes: int


class FileStore(Protocol):
    async def save(self, user_id: str, upload: UploadFile) -> StoredFile:
        """Validate and store one uploaded file. Raises HTTPException (and stores nothing) if it is not allowed."""
        ...

    def path(self, user_id: str, stored_name: str) -> Path:
        """Where the file is (it may be missing). Raises a 404 HTTPException for a name the store never makes."""
        ...

    def delete(self, user_id: str, stored_name: str) -> None: ...

    def iter_files(self, user_id: str) -> Iterator[tuple[Path, str]]:
        """Every file of the user as (absolute path, path relative to the store), for backups."""
        ...


class LocalFileStore:
    def __init__(self, base: Path) -> None:
        self.base = base

    def safe_path(self, user_id: str, stored_name: str) -> Path | None:
        if not _USER_ID_RE.match(user_id) or not _STORED_NAME_RE.match(stored_name):
            return None
        candidate = (self.base / user_id / stored_name).resolve()
        return candidate if candidate.is_relative_to(self.base) else None

    def path(self, user_id: str, stored_name: str) -> Path:
        path = self.safe_path(user_id, stored_name)
        if path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        return path

    def user_dir(self, user_id: str) -> Path:
        folder = self.base / user_id
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        return folder

    async def save(self, user_id: str, upload: UploadFile) -> StoredFile:
        settings = get_settings()
        max_bytes = settings.max_upload_bytes
        content_type, display_name = await _validated_type(upload, sanitize_filename(upload.filename))

        stored_name = f"{uuid.uuid4()}{ALLOWED_TYPES[content_type]}"
        destination = self.path(user_id, stored_name)
        self.user_dir(user_id)

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
        return StoredFile(stored_name, display_name, content_type, size)

    def delete(self, user_id: str, stored_name: str) -> None:
        path = self.safe_path(user_id, stored_name)
        if path is not None:
            remove_file(path)

    def iter_files(self, user_id: str) -> Iterator[tuple[Path, str]]:
        folder = self.base / user_id
        if not _USER_ID_RE.match(user_id) or not folder.is_dir():
            return
        for path in sorted(folder.iterdir()):
            if path.is_file() and _STORED_NAME_RE.match(path.name):
                yield path, path.relative_to(self.base).as_posix()


def get_file_store() -> LocalFileStore:
    return LocalFileStore(get_settings().files_path)


def ensure_storage_dirs() -> None:
    base = get_settings().files_path
    base.mkdir(parents=True, exist_ok=True)
    os.chmod(base, 0o700)


# ---------------------------------------------------------------- moving files from the old layout


def _move_file(source: Path, target: Path) -> None:
    """Move a file, also across disks: copy to a temporary name, check the size, then rename into place."""
    try:
        os.rename(source, target)
        return
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
    partial = target.with_name(f".{target.name}.partial")
    shutil.copyfile(source, partial)
    if partial.stat().st_size != source.stat().st_size:
        partial.unlink()
        raise OSError("copy is incomplete")
    os.chmod(partial, 0o600)
    os.replace(partial, target)
    source.unlink()


def relocate_legacy_files(db: Session, legacy_base: Path, files: LocalFileStore) -> tuple[int, int]:
    """Move files from UPLOAD_DIR/<type folder>/ to FILES_DIR/<user_id>/. Safe to run again after a crash.

    A document is marked as moved (storage_folder = "") only once its file is in the new place. Returns
    (moved, missing); missing files are left marked, so they are counted again on the next start.
    """
    rows = db.execute(
        select(Document, MedicalRecord.user_id)
        .join(MedicalRecord, Document.record_id == MedicalRecord.id)
        .where(Document.storage_folder != "")
    ).all()
    moved = missing = 0
    legacy_root = legacy_base.resolve()
    for document, user_id in rows:
        target = files.safe_path(user_id, document.stored_filename)
        source = (legacy_root / document.storage_folder / document.stored_filename).resolve()
        if target is None or document.storage_folder not in LEGACY_FOLDERS or not source.is_relative_to(legacy_root):
            missing += 1
            continue
        if not target.is_file():
            if not source.is_file():
                missing += 1
                continue
            files.user_dir(user_id)
            _move_file(source, target)
        document.storage_folder = ""
        db.commit()
        moved += 1

    if legacy_root.is_dir():
        for folder in [*(legacy_root / name for name in LEGACY_FOLDERS), legacy_root]:
            try:
                folder.rmdir()  # only succeeds when empty
            except OSError:
                pass
    if moved:
        logger.info("Moved %d stored files to the per-user folders", moved)
    if missing:
        logger.warning("%d documents have no file in the old upload folder or the new one", missing)
    return moved, missing
