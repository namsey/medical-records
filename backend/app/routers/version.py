"""Public build information (ctr-4): which image is running. Only the commit and version, nothing else."""

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(prefix="/api/version", tags=["version"], include_in_schema=False)


@router.get("")
def version() -> dict[str, str]:
    settings = get_settings()
    return {"commit": settings.app_commit.strip() or "dev", "version": settings.app_version.strip() or "dev"}
