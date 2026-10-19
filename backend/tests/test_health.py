"""#45: public health checks for the uptime monitor, and the admin's Server page."""

import logging
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.services import system_status

Usage = namedtuple("Usage", "total used free")
SECRET = "Okapiweed"


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def status_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "backup_status_dir", str(tmp_path))
    return tmp_path


def _disk_percent(monkeypatch, data: int, system: int) -> None:
    data_path = get_settings().sqlite_path.parent

    def fake(path):
        percent = data if str(path) == str(data_path) else system
        return Usage(100, percent, 100 - percent)

    monkeypatch.setattr(system_status.shutil, "disk_usage", fake)


def test_health_is_ok_when_the_database_answers(anon):
    response = anon.get("/api/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def test_health_fails_when_the_database_does_not(anon, monkeypatch):
    monkeypatch.setattr(system_status, "database_ok", lambda: False)
    response = anon.get("/api/health")
    assert (response.status_code, response.json()) == (503, {"status": "problem", "reason": "database_unavailable"})


@pytest.mark.parametrize(("data", "system", "ok"), [(79, 10, True), (80, 80, True), (81, 10, False), (10, 81, False)])
def test_disk_alert_above_80_percent_on_either_disk(anon, monkeypatch, data, system, ok):
    _disk_percent(monkeypatch, data, system)
    response = anon.get("/api/health/disk")
    if ok:
        assert (response.status_code, response.json()) == (200, {"status": "ok"})
    else:
        assert (response.status_code, response.json()) == (503, {"status": "problem", "reason": "disk_full"})


def test_backup_check_is_quiet_where_backups_are_not_set_up(anon):
    assert anon.get("/api/health/backup").json() == {"status": "ok", "note": "not_monitored"}


def test_backup_check(anon, status_dir):
    now = datetime.now(timezone.utc)

    def check():
        response = anon.get("/api/health/backup")
        return response.status_code, response.json().get("reason")

    assert check() == (503, "backup_missing")  # never ran
    (status_dir / "last-success").write_text(_stamp(now - timedelta(hours=3)) + "\n")
    assert check() == (200, None)
    (status_dir / "last-success").write_text(_stamp(now - timedelta(hours=27)))
    assert check() == (503, "backup_missing")  # stopped running
    (status_dir / "last-success").write_text(_stamp(now - timedelta(hours=3)))
    (status_dir / "last-failure").write_text(_stamp(now - timedelta(hours=1)))
    assert check() == (503, "backup_failed")  # failed tonight: alert at once
    (status_dir / "last-success").write_text(_stamp(now))
    assert check() == (200, None)  # a later success clears it
    (status_dir / "last-success").write_text("garbage")
    assert check() == (503, "backup_failed")


def test_public_checks_reveal_no_details(anon, status_dir, monkeypatch):
    _disk_percent(monkeypatch, 95, 95)
    for path in ("/api/health", "/api/health/disk", "/api/health/backup"):
        body = anon.get(path).text
        assert "95" not in body and str(status_dir) not in body and "/" not in body.replace("\\/", ""), path


def test_admin_server_page(client, second_client, status_dir, monkeypatch):
    _disk_percent(monkeypatch, 42, 17)
    success = datetime.now(timezone.utc) - timedelta(hours=2)
    (status_dir / "last-success").write_text(_stamp(success))
    system = client.get("/api/admin/system").json()
    assert system["disks"] == [{"name": "data", "percent_used": 42}, {"name": "system", "percent_used": 17}]
    assert system["disk_alert_percent"] == 80
    assert system["backup_state"] == "ok"
    assert system["last_backup_at"].startswith(success.strftime("%Y-%m-%dT%H:%M:%S"))
    assert system["last_backup_failure_at"] is None
    assert system["started_at"]
    assert second_client.get("/api/admin/system").status_code == 404


def test_server_errors_never_log_record_contents(client, make_record, monkeypatch, caplog):
    record = make_record(title=f"{SECRET} visit", reason=f"{SECRET} reason")

    def boom(*args, **kwargs):
        raise RuntimeError(f"failed while handling {SECRET}")

    monkeypatch.setattr("app.services.records.update_record", boom)
    caplog.set_level(logging.DEBUG)
    from fastapi.testclient import TestClient

    from app.main import app
    from tests.conftest import CSRF_HEADERS

    quiet = TestClient(app, headers=CSRF_HEADERS, raise_server_exceptions=False, cookies=client.cookies)
    response = quiet.put(f"/api/records/{record['id']}", json={"record_type": "doctor_visit", "record_date": "2026-01-01",
                                                                "reason": f"{SECRET} new"})
    assert response.status_code == 500
    assert SECRET not in response.text
    assert caplog.records, "the error should be logged"
    assert all(SECRET not in entry.getMessage() for entry in caplog.records)
