"""Migration 0003 (invites and roles): the admin stays in, other old accounts start disabled, no data changes."""

import sqlite3

from tests.test_migration_0002 import _migrate, _rows, _seed_0001


def test_admin_gets_the_role_and_other_accounts_start_disabled(tmp_path):
    database = tmp_path / "old.db"
    _seed_0001(database, users=[("u-owner", "Owner@Example.com"), ("u-other", "old@example.com")])
    _migrate(database, "0002")
    before = _rows(database)

    _migrate(database, "head")

    assert _rows(database) == before
    connection = sqlite3.connect(database)
    try:
        users = dict(
            (email, (role, disabled))
            for email, role, disabled in connection.execute("SELECT email, role, disabled_at FROM users")
        )
        assert users["Owner@Example.com"] == ("admin", None)
        assert users["old@example.com"][0] == "user"
        assert users["old@example.com"][1] is not None
        assert connection.execute("SELECT count(*) FROM invites").fetchone()[0] == 0
    finally:
        connection.close()


def test_0004_gives_every_existing_account_the_default_storage_limit(tmp_path):
    database = tmp_path / "old.db"
    _seed_0001(database, users=[("u-owner", "owner@example.com"), ("u-other", "old@example.com")])
    _migrate(database, "0003")
    before = _rows(database)
    _migrate(database, "0004")
    assert _rows(database) == before
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT quota_bytes FROM users").fetchall() == [(None,), (None,)]
    finally:
        connection.close()


def test_0005_asks_every_existing_account_for_consent_and_adds_the_audit_log(tmp_path):
    database = tmp_path / "old.db"
    _seed_0001(database, users=[("u-owner", "owner@example.com")])
    _migrate(database, "0004")
    before = _rows(database)
    _migrate(database, "0005")
    assert _rows(database) == before
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT consent_version, consented_at FROM users").fetchall() == [(None, None)]
        assert connection.execute("SELECT count(*) FROM audit_events").fetchone()[0] == 0
    finally:
        connection.close()
