"""Document upload, authenticated viewing / download, and deletion."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile

from app.models import Document
from app.schemas import DocumentOut
from app.security import private_dependencies
from app.services import rate_limit
from app.services.record_store import RecordStore, get_record_store

router = APIRouter(prefix="/api", tags=["documents"], dependencies=private_dependencies)

MAX_FILES_PER_REQUEST = 20
FILE_HEADERS = {
    "Cache-Control": "private, no-store",
    "X-Content-Type-Options": "nosniff",
}


def _file_response(store: RecordStore, document: Document, disposition: str) -> FileResponse:
    path = store.document_path(document)
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
async def upload_documents(
    record_id: str, request: Request, store: RecordStore = Depends(get_record_store)
) -> list[DocumentOut]:
    """Upload one or more files (multipart form, any field name). All files are stored or none are."""
    record = store.get(record_id, full=False)

    async with request.form(max_files=MAX_FILES_PER_REQUEST, max_fields=20) as form:
        uploads = [value for _, value in form.multi_items() if isinstance(value, UploadFile)]
        if not uploads:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No file was uploaded")
        rate_limit.enforce(
            rate_limit.UPLOADED_FILES, store.user_id, "Too many files uploaded in the last hour.", cost=len(uploads)
        )
        saved = await store.add_documents(record, uploads)
    return [DocumentOut.model_validate(document) for document in saved]


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, store: RecordStore = Depends(get_record_store)) -> DocumentOut:
    return DocumentOut.model_validate(store.get_document(document_id))


@router.get("/documents/{document_id}/view")
def view_document(document_id: str, store: RecordStore = Depends(get_record_store)) -> FileResponse:
    """Serve the file for in-browser viewing (inline)."""
    return _file_response(store, store.get_document(document_id), "inline")


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, store: RecordStore = Depends(get_record_store)) -> FileResponse:
    return _file_response(store, store.get_document(document_id), "attachment")


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, store: RecordStore = Depends(get_record_store)) -> Response:
    store.delete_document(store.get_document(document_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
