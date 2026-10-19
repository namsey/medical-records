"""Guards that keep new code inside the data-separation rules (#39)."""

import re
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

from app.main import app

# The only /api routes that work without a session.
PUBLIC_ROUTES = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/login"),
    ("GET", "/api/auth/callback"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/invite/{token}"),  # only says whether an invite link is still usable
}


def _api_routes(routes) -> list[APIRoute]:
    """Every APIRoute, including those inside included routers."""
    found = []
    for route in routes:
        if isinstance(route, APIRoute):
            found.append(route)
        elif hasattr(route, "original_router"):
            found += _api_routes(route.original_router.routes)
    return found


API_ROUTES = sorted(
    (method, route.path)
    for route in _api_routes(app.routes)
    if route.path.startswith("/api/")
    for method in route.methods
)


def test_route_list_is_not_empty():
    assert len(API_ROUTES) > 20
    assert PUBLIC_ROUTES <= set(API_ROUTES)


@pytest.mark.parametrize(("method", "path"), [r for r in API_ROUTES if r not in PUBLIC_ROUTES])
def test_every_other_api_route_needs_a_session(anon, method, path):
    """Found from the app itself, so a new route cannot be missed by forgetting to list it."""
    url = re.sub(r"\{[^}]+\}", "x", path)
    assert anon.request(method, url).status_code == 401


@pytest.mark.parametrize(("method", "path"), [r for r in API_ROUTES if r[1].startswith("/api/admin/")])
def test_admin_routes_are_not_found_for_other_users(second_client, method, path):
    url = re.sub(r"\{[^}]+\}", "x", path)
    response = second_client.request(method, url, json={"email": "a@example.com", "confirm_email": "x"})
    assert (response.status_code, response.json()) == (404, {"detail": "Not found"})


def test_there_are_admin_routes():
    assert sum(1 for _, path in API_ROUTES if path.startswith("/api/admin/")) >= 7


ROUTERS = Path(__file__).resolve().parents[1] / "app" / "routers"
# Data access goes through RecordStore, which always filters by the signed-in user.
DIRECT_QUERY = re.compile(r"\bsqlalchemy\b|\bselect\(|\bdb\.(get|query|execute|scalar|scalars|add|delete)\(|\bSession\b")


@pytest.mark.parametrize("router", sorted(p.name for p in ROUTERS.glob("*.py") if p.name not in {"__init__.py", "auth.py"}))
def test_routers_do_not_query_the_database_directly(router):
    source = (ROUTERS / router).read_text()
    assert not DIRECT_QUERY.search(source), f"{router} queries the database; use RecordStore instead"
