"""Server health for monitoring: database, disk space and backups.

The public health checks only say ok or problem (with a reason code), never numbers, paths or user data; the
admin's Server page gets the details.
"""

import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal

STARTED_AT = datetime.now(timezone.utc)


def database_ok() -> bool:
    try:
        with SessionLocal() as db:
            return db.execute(text("SELECT 1")).scalar() == 1
    except Exception:  # noqa: BLE001 - any failure means the database cannot be used
        return False


@dataclass
class Disk:
    name: str
    percent_used: int


def disks() -> list[Disk]:
    """Space used on the disk holding the data folder, and on the system disk."""
    settings = get_settings()
    result = []
    for name, path in (("data", settings.sqlite_path.parent), ("system", Path("/"))):
        usage = shutil.disk_usage(path if path.exists() else Path("/"))
        result.append(Disk(name, round(usage.used * 100 / usage.total) if usage.total else 0))
    return result


def disk_problem() -> str | None:
    limit = get_settings().disk_alert_percent
    return "disk_full" if any(disk.percent_used > limit for disk in disks()) else None


@dataclass
class BackupState:
    state: str  # ok, backup_failed, backup_missing or not_monitored
    last_success: datetime | None
    last_failure: datetime | None


def _read_time(path: Path) -> datetime | None:
    try:
        value = path.read_text().strip()
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (OSError, ValueError):
        return None


def backup_state() -> BackupState:
    """From the times scripts/backup.sh writes: a failure newer than the last success, or no success within
    BACKUP_MAX_AGE_HOURS, is a problem."""
    settings = get_settings()
    if not settings.backup_status_dir.strip():
        return BackupState("not_monitored", None, None)
    folder = Path(settings.backup_status_dir)
    success = _read_time(folder / "last-success")
    failure = _read_time(folder / "last-failure")
    if failure and (success is None or failure > success):
        state = "backup_failed"
    elif success is None or datetime.now(timezone.utc) - success > timedelta(hours=settings.backup_max_age_hours):
        state = "backup_missing"
    else:
        state = "ok"
    return BackupState(state, success, failure)
