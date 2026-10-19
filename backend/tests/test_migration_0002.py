"""Migration 0002 (record ownership) on a copy of a database in the 0001 shape: nothing is lost or changed."""

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, event

from app.migrations import alembic_config, snapshot_before_migrations

OWNER_EMAIL = "owner@example.com"  # ALLOWED_EMAIL in conftest


def _migrate(database: Path, revision: str, *, foreign_keys: bool = False) -> None:
    engine = create_engine(f"sqlite:///{database}")
    if foreign_keys:
        event.listen(engine, "connect", lambda connection, _record: connection.execute("PRAGMA foreign_keys=ON"))
    try:
        with engine.begin() as connection:
            config = alembic_config()
            config.attributes["connection"] = connection
            command.upgrade(config, revision)
    finally:
        engine.dispose()


def _seed_0001(database: Path, *, users: list[tuple[str, str]] = ()) -> None:
    """A little of everything, written the way version 0001 of the app stored it."""
    _migrate(database, "0001")
    now = "2026-10-01 09:00:00.000000"
    connection = sqlite3.connect(database)
    with connection:
        for user_id, email in users:
            connection.execute("INSERT INTO users VALUES (?, ?, 'Someone', ?, NULL)", (user_id, email, now))
        connection.execute(
            "INSERT INTO doctors (id, name, created_at, updated_at) VALUES ('d1', 'Dr. Rao', ?, ?)", (now, now)
        )
        connection.execute("INSERT INTO labs (id, name, created_at, updated_at) VALUES ('l1', 'City Lab', ?, ?)", (now, now))
        connection.execute("INSERT INTO tags VALUES ('t1', 'Thyroid', 'thyroid'), ('t2', 'Yearly', 'yearly')")
        for record_id, record_type, doctor, lab in (
            ("r1", "prescription", "d1", None),
            ("r2", "lab_report", None, "l1"),
            ("r3", "scan", None, None),
        ):
            connection.execute(
                "INSERT INTO medical_records (id, record_type, title, record_date, doctor_id, lab_id, personal_notes, "
                "created_at, updated_at) VALUES (?, ?, ?, '2026-09-05', ?, ?, 'private note', ?, ?)",
                (record_id, record_type, f"Title {record_id}", doctor, lab, now, now),
            )
        connection.execute("INSERT INTO prescription_medicines (id, record_id, position, name) VALUES ('m1', 'r1', 0, 'Thyronorm')")
        connection.execute("INSERT INTO lab_results (id, record_id, position, parameter) VALUES ('x1', 'r2', 0, 'TSH')")
        connection.execute("INSERT INTO record_tags VALUES ('r1', 't1'), ('r2', 't1'), ('r2', 't2')")
        connection.execute(
            "INSERT INTO documents VALUES ('doc1', 'r3', 'xray.png', "
            "'00000000-0000-0000-0000-000000000001.png', 'scans', 'image/png', 10, ?)",
            (now,),
        )
    connection.close()


def _rows(database: Path) -> dict[str, list[tuple]]:
    """Every row of every data table, minus the new user_id columns, for a before/after comparison."""
    connection = sqlite3.connect(database)
    try:
        result = {}
        for table in ("doctors", "labs", "tags", "medical_records", "prescription_medicines", "lab_results",
                      "record_tags", "documents"):
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})") if row[1] != "user_id"]
            result[table] = connection.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY 1, 2").fetchall()
        return result
    finally:
        connection.close()


def _owners(database: Path) -> set[str]:
    connection = sqlite3.connect(database)
    try:
        return {
            owner
            for table in ("doctors", "labs", "tags", "medical_records")
            for (owner,) in connection.execute(f"SELECT user_id FROM {table}")
        }
    finally:
        connection.close()


def test_existing_data_is_kept_and_given_to_the_owner(tmp_path):
    database = tmp_path / "old.db"
    _seed_0001(database, users=[("u-owner", "Owner@Example.com"), ("u-other", "someone@example.com")])
    before = _rows(database)

    _migrate(database, "head")

    assert _rows(database) == before
    assert _owners(database) == {"u-owner"}


def test_owner_account_is_created_when_it_never_signed_in(tmp_path):
    database = tmp_path / "old.db"
    _seed_0001(database)
    before = _rows(database)

    _migrate(database, "head")

    assert _rows(database) == before
    connection = sqlite3.connect(database)
    users = connection.execute("SELECT id, email FROM users").fetchall()
    connection.close()
    assert [email for _, email in users] == [OWNER_EMAIL]
    assert _owners(database) == {users[0][0]}


def test_empty_database_gets_no_owner_row(tmp_path):
    database = tmp_path / "empty.db"
    _migrate(database, "0001")
    _migrate(database, "head")
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 0
    connection.close()


def test_tag_names_are_unique_per_user(tmp_path):
    database = tmp_path / "old.db"
    _seed_0001(database, users=[("u-owner", OWNER_EMAIL), ("u-other", "someone@example.com")])
    _migrate(database, "head")
    connection = sqlite3.connect(database)
    with connection:
        connection.execute("INSERT INTO tags VALUES ('t3', 'Thyroid', 'thyroid', 'u-other')")
    with pytest.raises(sqlite3.IntegrityError), connection:
        connection.execute("INSERT INTO tags VALUES ('t4', 'THYROID', 'thyroid', 'u-owner')")
    connection.close()


def test_refuses_to_run_with_foreign_keys_on(tmp_path):
    """Batch mode drops and recreates tables; with foreign keys on, that would cascade-delete child rows."""
    database = tmp_path / "old.db"
    _seed_0001(database)
    before = _rows(database)
    with pytest.raises(RuntimeError, match="foreign keys"):
        _migrate(database, "head", foreign_keys=True)
    assert _rows(database) == before


def test_snapshot_is_taken_only_when_a_migration_is_pending(tmp_path):
    database = tmp_path / "old.db"
    backups = tmp_path / "backups"
    _seed_0001(database)
    before = _rows(database)

    snapshot = snapshot_before_migrations(database, backups)
    assert snapshot is not None and snapshot.parent == backups
    assert snapshot.name.startswith("pre-0002-")
    assert _rows(snapshot) == before
    assert snapshot.stat().st_mode & 0o777 == 0o600

    _migrate(database, "head")
    assert snapshot_before_migrations(database, backups) is None
    assert snapshot_before_migrations(tmp_path / "missing.db", backups) is None
    assert list(backups.iterdir()) == [snapshot]
