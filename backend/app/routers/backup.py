"""Full backup (ZIP) and structured JSON export."""

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.security import private_dependencies
from app.services import backup
from app.services.record_store import RecordStore, get_record_store

router = APIRouter(prefix="/api", tags=["backup"], dependencies=private_dependencies)

DOWNLOAD_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


@router.get("/backup")
def download_backup(store: RecordStore = Depends(get_record_store)) -> FileResponse:
    """ZIP with a copy of the database holding only the signed-in user's data, and that user's files."""
    archive = store.backup_zip()
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=backup.backup_filename(),
        headers=DOWNLOAD_HEADERS,
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )


@router.get("/export/json")
def export_json(store: RecordStore = Depends(get_record_store)) -> Response:
    """The signed-in user's doctors, laboratories and records (with medicines / results / tags / document metadata)."""
    return Response(
        content=store.export_json(),
        media_type="application/json",
        headers={
            **DOWNLOAD_HEADERS,
            "Content-Disposition": f'attachment; filename="{backup.export_filename()}"',
        },
    )
