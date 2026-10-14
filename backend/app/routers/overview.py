"""Tags, record years and the chronological timeline."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import MedicalRecord, Tag, record_tags
from app.routers.records import get_filters
from app.schemas import TagOut, TimelineItem, YearCount
from app.security import private_dependencies
from app.services import records as record_service
from app.services.search import RecordFilters, search_records

router = APIRouter(prefix="/api", tags=["overview"], dependencies=private_dependencies)


@router.get("/tags", response_model=list[TagOut])
def list_tags(db: Session = Depends(get_db)) -> list[TagOut]:
    rows = db.execute(
        select(Tag.name, func.count(record_tags.c.record_id))
        .join(record_tags, record_tags.c.tag_id == Tag.id)
        .group_by(Tag.id)
        .order_by(func.lower(Tag.name))
    ).all()
    return [TagOut(name=name, record_count=count) for name, count in rows]


@router.get("/years", response_model=list[YearCount])
def list_years(db: Session = Depends(get_db)) -> list[YearCount]:
    """Every year that has records, newest first, for the year filter chips."""
    year = func.strftime("%Y", MedicalRecord.record_date)
    rows = db.execute(select(year, func.count(MedicalRecord.id)).group_by(year).order_by(year.desc())).all()
    return [YearCount(year=int(value), record_count=count) for value, count in rows]


@router.get("/timeline", response_model=list[TimelineItem])
def timeline(filters: RecordFilters = Depends(get_filters), db: Session = Depends(get_db)) -> list[TimelineItem]:
    """Every matching record, in date order (newest first unless `sort=oldest`). The client groups by year / day."""
    items, _ = search_records(db, filters, limit=None)
    return [record_service.to_timeline_item(item) for item in items]


@router.get("/config")
def app_config() -> dict[str, int | list[str]]:
    """Settings the web app needs for friendly client-side checks (the server enforces them again)."""
    return {
        "max_upload_mb": get_settings().max_upload_size_mb,
        "allowed_extensions": [".pdf", ".jpg", ".jpeg", ".png", ".webp"],
    }
