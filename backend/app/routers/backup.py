"""Full backup (ZIP) and structured JSON export."""

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app.database import get_db
from app.security import private_dependencies
from app.services import backup

router = APIRouter(prefix="/api", tags=["backup"], dependencies=private_dependencies)

DOWNLOAD_HEADERS = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}


@router.get("/backup")
def download_backup() -> FileResponse:
    """ZIP containing the SQLite database and every uploaded file."""
    archive = backup.create_backup_zip()
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=backup.backup_filename(),
        headers=DOWNLOAD_HEADERS,
        background=BackgroundTask(archive.unlink, missing_ok=True),
    )


@router.get("/export/json")
def export_json(db: Session = Depends(get_db)) -> Response:
    """All structured records (doctors, laboratories, records with medicines / results / tags / document metadata)."""
    return Response(
        content=backup.build_json_export(db),
        media_type="application/json",
        headers={
            **DOWNLOAD_HEADERS,
            "Content-Disposition": f'attachment; filename="{backup.export_filename()}"',
        },
    )
