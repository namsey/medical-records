"""Public health checks for an outside uptime monitor (DEPLOY.md, "Monitoring and alerts").

Each answers 200 {"status": "ok"} or 503 {"status": "problem", "reason": ...}. Nothing else: no numbers, paths or
user data. They need no session, so a monitor can call them; they only read server state.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.services import system_status

router = APIRouter(prefix="/api/health", tags=["health"], include_in_schema=False)


def _answer(problem: str | None, ok: str | None = None) -> JSONResponse:
    if problem:
        return JSONResponse({"status": "problem", "reason": problem}, status_code=503)
    return JSONResponse({"status": "ok", **({"note": ok} if ok else {})})


@router.get("")
def health() -> JSONResponse:
    """The app answers and can use its database (also fails when the whole server is down)."""
    return _answer(None if system_status.database_ok() else "database_unavailable")


@router.get("/disk")
def disk() -> JSONResponse:
    """The data disk and the system disk are each at most DISK_ALERT_PERCENT full."""
    return _answer(system_status.disk_problem())


@router.get("/backup")
def backup() -> JSONResponse:
    """The last backup run succeeded, within BACKUP_MAX_AGE_HOURS."""
    state = system_status.backup_state().state
    if state == "not_monitored":
        return _answer(None, "not_monitored")
    return _answer(None if state == "ok" else state)
