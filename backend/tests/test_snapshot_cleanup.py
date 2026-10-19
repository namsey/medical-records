"""sec-3: only the 3 newest pre-migration database copies are kept, and only after a successful upgrade."""

import logging
import sqlite3

import pytest

from alembic.script import ScriptDirectory

from app import migrations
from app.config import get_settings
from app.migrations import alembic_config, prune_snapshots, run_migrations
from tests.test_migration_0002 import _seed_0001

OLD = [f"pre-000{n}_old-2026010{n}T000000Z.db" for n in range(1, 6)]  # oldest first


def _make(backups, names):
    backups.mkdir(parents=True, exist_ok=True)
    for name in names:
        (backups / name).write_bytes(b"copy")


def test_prune_keeps_the_three_newest_and_logs_only_the_count(tmp_path, caplog):
    backups = tmp_path / "backups"
    # Newest by time even though its revision sorts first.
    _make(backups, [*OLD, "pre-0000_first-20260201T000000Z.db", "notes.txt"])
    with caplog.at_level(logging.INFO, logger="app.migrations"):
        assert prune_snapshots(backups) == 3
    assert sorted(p.name for p in backups.iterdir()) == sorted(
        ["pre-0000_first-20260201T000000Z.db", OLD[3], OLD[4], "notes.txt"]
    )
    assert "Deleted 3 old pre-migration database copies" in caplog.text
    assert str(tmp_path) not in caplog.text and "pre-0" not in caplog.text
    assert prune_snapshots(backups) == 0
    assert prune_snapshots(tmp_path / "missing") == 0


def _point_at(monkeypatch, database):
    monkeypatch.setattr(get_settings(), "database_url", f"sqlite:///{database}")


def test_successful_upgrade_keeps_the_new_copy_and_two_older(tmp_path, monkeypatch):
    database = tmp_path / "medical_records.db"
    backups = tmp_path / "backups"
    _seed_0001(database)
    _make(backups, OLD)
    _point_at(monkeypatch, database)

    run_migrations()

    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert sqlite3.connect(database).execute("SELECT version_num FROM alembic_version").fetchone()[0] == head
    left = sorted(p.name for p in backups.iterdir())
    assert len(left) == 3
    assert OLD[3] in left and OLD[4] in left
    new = next(name for name in left if name not in OLD)
    assert new.startswith("pre-")


def test_failed_upgrade_deletes_no_copies(tmp_path, monkeypatch):
    database = tmp_path / "medical_records.db"
    backups = tmp_path / "backups"
    _seed_0001(database)
    _make(backups, OLD)
    _point_at(monkeypatch, database)

    def fail(*_args, **_kwargs):
        raise RuntimeError("upgrade failed")

    monkeypatch.setattr(migrations.command, "upgrade", fail)
    with pytest.raises(RuntimeError, match="upgrade failed"):
        run_migrations()
    assert len(list(backups.iterdir())) == len(OLD) + 1  # the old copies plus the one taken before this upgrade
