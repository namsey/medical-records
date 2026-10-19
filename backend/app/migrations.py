"""Run Alembic migrations programmatically so the app always starts on an up-to-date schema."""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import BACKEND_ROOT, get_settings

logger = logging.getLogger(__name__)

KEEP_SNAPSHOTS = 3


def alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


def _current_revision(database: Path) -> str | None:
    connection = sqlite3.connect(database)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        connection.close()
    return row[0] if row else None


def snapshot_before_migrations(database: Path, backups_dir: Path) -> Path | None:
    """Copy an existing database before migrations change it. Returns the snapshot path, or None if not needed."""
    if not database.is_file():
        return None
    current = _current_revision(database)
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if current is None or current == head:
        return None
    backups_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(backups_dir, 0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot = backups_dir / f"pre-{head}-{stamp}.db"
    source = sqlite3.connect(database)
    target = sqlite3.connect(snapshot)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    os.chmod(snapshot, 0o600)
    logger.info("Saved a copy of the database before migrating to revision %s", head)
    return snapshot


def prune_snapshots(backups_dir: Path, keep: int = KEEP_SNAPSHOTS) -> int:
    """Delete all but the `keep` newest pre-migration snapshots. Returns how many were deleted."""
    if not backups_dir.is_dir():
        return 0
    # Names are pre-<revision>-<UTC time>.db, so the part after the last "-" sorts by age.
    snapshots = sorted(backups_dir.glob("pre-*.db"), key=lambda path: path.stem.rsplit("-", 1)[-1], reverse=True)
    old = snapshots[keep:]
    for path in old:
        path.unlink(missing_ok=True)
    if old:
        logger.info("Deleted %d old pre-migration database copies", len(old))
    return len(old)


def run_migrations() -> None:
    database = get_settings().sqlite_path
    backups_dir = database.parent / "backups"
    snapshot_before_migrations(database, backups_dir)
    command.upgrade(alembic_config(), "head")
    # Only after a successful upgrade: if it fails, every copy stays for the restore.
    prune_snapshots(backups_dir)
