"""Tags, record years and the chronological timeline."""

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.routers.records import get_filters
from app.schemas import StorageOut, TagOut, TimelineItem, YearCount
from app.security import private_dependencies
from app.services import records as record_service
from app.services import storage
from app.services.record_store import RecordStore, get_record_store
from app.services.search import RecordFilters

router = APIRouter(prefix="/api", tags=["overview"], dependencies=private_dependencies)


@router.get("/tags", response_model=list[TagOut])
def list_tags(store: RecordStore = Depends(get_record_store)) -> list[TagOut]:
    return [TagOut(name=name, record_count=count) for name, count in store.tags()]


@router.get("/years", response_model=list[YearCount])
def list_years(store: RecordStore = Depends(get_record_store)) -> list[YearCount]:
    """Every year that has records, newest first, for the year filter chips."""
    return [YearCount(year=year, record_count=count) for year, count in store.years()]


@router.get("/timeline", response_model=list[TimelineItem])
def timeline(
    filters: RecordFilters = Depends(get_filters), store: RecordStore = Depends(get_record_store)
) -> list[TimelineItem]:
    """Every matching record, in date order (newest first unless `sort=oldest`). The client groups by year / day."""
    items, _ = store.search(filters, limit=None)
    return [record_service.to_timeline_item(item) for item in items]


@router.get("/storage", response_model=StorageOut)
def storage_use(store: RecordStore = Depends(get_record_store)) -> StorageOut:
    """How much of the account's storage limit is used."""
    return StorageOut(used_bytes=store.storage_used_bytes(), quota_bytes=store.quota_bytes())


@router.get("/config")
def app_config() -> dict[str, int | list[str]]:
    """Settings the web app needs for friendly client-side checks (the server enforces them again)."""
    return {
        "max_upload_mb": get_settings().max_upload_size_mb,
        "allowed_extensions": sorted(storage.ALLOWED_EXTENSIONS),
    }
