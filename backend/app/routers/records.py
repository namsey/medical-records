"""Medical record CRUD and filtered listing."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import RecordIn, RecordOut, RecordPage, RecordType
from app.security import private_dependencies
from app.services import records as record_service
from app.services.search import RecordFilters, search_records

router = APIRouter(prefix="/api", tags=["records"], dependencies=private_dependencies)


def get_filters(
    q: str | None = Query(default=None, max_length=200),
    record_type: list[RecordType] = Query(default=[]),
    tag: list[str] = Query(default=[], max_length=20),
    date_from: date | None = None,
    date_to: date | None = None,
    doctor_id: str | None = Query(default=None, max_length=36),
    lab_id: str | None = Query(default=None, max_length=36),
    sort: Literal["newest", "oldest"] = "newest",
) -> RecordFilters:
    return RecordFilters(
        q=(q or "").strip() or None,
        record_types=record_type,
        tags=tag,
        date_from=date_from,
        date_to=date_to,
        doctor_id=doctor_id,
        lab_id=lab_id,
        sort=sort,
    )


def list_records(
    filters: RecordFilters = Depends(get_filters),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> RecordPage:
    items, total = search_records(db, filters, limit, offset)
    return RecordPage(
        items=[record_service.to_summary(item) for item in items], total=total, limit=limit, offset=offset
    )


# `/records` (browse + filter) and `/search` (same filters, with `q`) share one implementation.
router.add_api_route("/records", list_records, methods=["GET"], response_model=RecordPage)
router.add_api_route("/search", list_records, methods=["GET"], response_model=RecordPage)


@router.post("/records", response_model=RecordOut, status_code=status.HTTP_201_CREATED)
def create_record(payload: RecordIn, db: Session = Depends(get_db)) -> RecordOut:
    record = record_service.create_record(db, payload)
    return RecordOut.model_validate(record)


@router.get("/records/{record_id}", response_model=RecordOut)
def get_record(record_id: str, db: Session = Depends(get_db)) -> RecordOut:
    return RecordOut.model_validate(record_service.get_record_or_404(db, record_id))


@router.put("/records/{record_id}", response_model=RecordOut)
def update_record(record_id: str, payload: RecordIn, db: Session = Depends(get_db)) -> RecordOut:
    record = record_service.get_record_or_404(db, record_id)
    return RecordOut.model_validate(record_service.update_record(db, record, payload))


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(record_id: str, db: Session = Depends(get_db)) -> Response:
    record = record_service.get_record_or_404(db, record_id)
    record_service.delete_record(db, record)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
