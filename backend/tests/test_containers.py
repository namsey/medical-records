"""ctr-4: settings for running in a container behind a proxy container."""

import sys

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import app.__main__ as entrypoint
from app.config import get_settings
from app.main import app
from app.services import rate_limit, system_status
from tests.conftest import CSRF_HEADERS
from tests.test_health import Usage

PROXY_IP = "172.30.0.10"


@pytest.fixture
def server_options(monkeypatch):
    """The options `python -m app` gives uvicorn (uvicorn.run is replaced, so nothing starts)."""
    captured = {}
    monkeypatch.setattr(entrypoint.uvicorn, "run", lambda *args, **kwargs: captured.update(kwargs))
    monkeypatch.setattr(sys, "argv", ["app", "--host", "0.0.0.0"])

    def run(**settings) -> dict:
        for name, value in settings.items():
            monkeypatch.setattr(get_settings(), name, value)
        entrypoint.main()
        return captured

    return run


def test_uvicorn_trusts_only_127_0_0_1_by_default_and_waits_30s_on_shutdown(server_options):
    options = server_options()
    assert options["proxy_headers"] is True
    assert options["forwarded_allow_ips"] == "127.0.0.1"
    assert options["timeout_graceful_shutdown"] == 30


def test_uvicorn_gets_the_proxy_address_and_grace_period_from_the_settings(server_options):
    options = server_options(forwarded_allow_ips=PROXY_IP, shutdown_grace_seconds=12)
    assert (options["forwarded_allow_ips"], options["timeout_graceful_shutdown"]) == (PROXY_IP, 12)


def _client_from(peer: str, forwarded_allow_ips: str) -> TestClient:
    """The app as uvicorn serves it with these settings, called from the address `peer`."""
    proxied = ProxyHeadersMiddleware(app, trusted_hosts=forwarded_allow_ips)
    return TestClient(proxied, headers=CSRF_HEADERS, client=(peer, 40000))


def test_rate_limits_use_the_forwarded_client_ip_from_an_allowed_proxy(server_options):
    allowed = server_options(forwarded_allow_ips=PROXY_IP)["forwarded_allow_ips"]
    client = _client_from(PROXY_IP, allowed)
    first = {"X-Forwarded-For": "198.51.100.7"}
    for _ in range(rate_limit.INVITE_CHECKS.limit):
        assert client.get("/api/auth/invite/guess", headers=first).status_code == 200
    assert client.get("/api/auth/invite/guess", headers=first).status_code == 429
    # Another user behind the same proxy has their own budget.
    assert client.get("/api/auth/invite/guess", headers={"X-Forwarded-For": "198.51.100.8"}).status_code == 200


def test_rate_limits_ignore_x_forwarded_for_from_other_addresses(server_options):
    allowed = server_options(forwarded_allow_ips=PROXY_IP)["forwarded_allow_ips"]
    client = _client_from("172.30.0.99", allowed)
    for n in range(rate_limit.INVITE_CHECKS.limit):
        assert client.get("/api/auth/invite/guess", headers={"X-Forwarded-For": f"198.51.100.{n}"}).status_code == 200
    # A made-up header per request does not get a fresh budget: the peer address is the key.
    assert client.get("/api/auth/invite/guess", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 429


def test_version_is_dev_when_the_build_did_not_set_it(anon):
    assert anon.get("/api/version").json() == {"commit": "dev", "version": "dev"}


def test_version_shows_only_the_build_commit_and_version(anon, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_commit", "0123abc")
    monkeypatch.setattr(get_settings(), "app_version", "v1.2.0")
    response = anon.get("/api/version")
    assert (response.status_code, response.json()) == (200, {"commit": "0123abc", "version": "v1.2.0"})


def _full_system_disk(monkeypatch) -> None:
    """The data disk is 10% full, every other path 99%."""
    data_path = str(get_settings().sqlite_path.parent)

    def fake(path):
        percent = 10 if str(path) == data_path else 99
        return Usage(100, percent, 100 - percent)

    monkeypatch.setattr(system_status.shutil, "disk_usage", fake)


def test_the_system_disk_is_checked_at_root_by_default(anon, monkeypatch):
    _full_system_disk(monkeypatch)
    assert [(d.name, d.percent_used) for d in system_status.disks()] == [("data", 10), ("system", 99)]
    assert anon.get("/api/health/disk").json() == {"status": "problem", "reason": "disk_full"}


def test_an_empty_system_disk_path_checks_only_the_data_disk(anon, monkeypatch):
    _full_system_disk(monkeypatch)
    monkeypatch.setattr(get_settings(), "system_disk_path", "")
    assert [(d.name, d.percent_used) for d in system_status.disks()] == [("data", 10)]
    assert anon.get("/api/health/disk").json() == {"status": "ok"}


def test_the_data_disk_is_still_checked_without_a_system_disk(anon, monkeypatch):
    monkeypatch.setattr(get_settings(), "system_disk_path", "")
    monkeypatch.setattr(system_status.shutil, "disk_usage", lambda path: Usage(100, 95, 5))
    assert anon.get("/api/health/disk").json() == {"status": "problem", "reason": "disk_full"}
