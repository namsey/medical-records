"""Document upload, authenticated viewing / download, and deletion."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.database import get_db
from app.models import Document
from app.schemas import DocumentOut
from app.security import private_dependencies
from app.services import records as record_service
from app.services import storage

router = APIRouter(prefix="/api", tags=["documents"], dependencies=private_dependencies)

MAX_FILES_PER_REQUEST = 20
FILE_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}


def _get_document(db: Session, document_id: str) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def _file_response(document: Document, disposition: str) -> FileResponse:
    path = storage.stored_path(document)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The file is missing from storage")
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type=disposition,
        headers=FILE_HEADERS,
    )


@router.post(
    "/records/{record_id}/documents",
    response_model=list[DocumentOut],
    status_code=status.HTTP_201_CREATED,
)
async def upload_documents(record_id: str, request: Request, db: Session = Depends(get_db)) -> list[DocumentOut]:
    """Upload one or more files (multipart form, any field name). All files are stored or none are."""
    record = record_service.get_record_or_404(db, record_id, full=False)

    saved: list[Document] = []
    async with request.form(max_files=MAX_FILES_PER_REQUEST, max_fields=20) as form:
        uploads = [value for _, value in form.multi_items() if isinstance(value, UploadFile)]
        if not uploads:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file was uploaded")
        try:
            for upload in uploads:
                saved.append(await storage.save_upload(upload, record))
            db.add_all(saved)
            db.commit()
        except BaseException:
            db.rollback()
            for document in saved:
                storage.remove_file(storage.stored_path(document))
            raise
    return [DocumentOut.model_validate(document) for document in saved]


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentOut:
    return DocumentOut.model_validate(_get_document(db, document_id))


@router.get("/documents/{document_id}/view")
def view_document(document_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """Serve the file for in-browser viewing (inline)."""
    return _file_response(_get_document(db, document_id), "inline")


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db)) -> FileResponse:
    return _file_response(_get_document(db, document_id), "attachment")


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> Response:
    document = _get_document(db, document_id)
    path = storage.stored_path(document)
    db.delete(document)
    db.commit()
    storage.remove_file(path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
