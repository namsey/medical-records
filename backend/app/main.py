"""FastAPI application: private JSON API under /api, plus the built React app for everything else."""

import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse

from app.config import FRONTEND_DIST, get_settings
from app.database import SessionLocal
from app.middleware import MaxBodySizeMiddleware, SecurityHeadersMiddleware
from app.migrations import run_migrations
from app.routers import account, admin, auth, backup, directories, documents, health, overview, records
from app.services import audit, sessions, storage

logger = logging.getLogger("app")

# Request URLs can contain search terms (medical data), so the per-request access log stays off.
logging.getLogger("uvicorn.access").disabled = True

# Module workers and WebAssembly (used by the PDF viewer) are only accepted with the right content types,
# which the OS mime table does not always provide.
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")

UPLOAD_OVERHEAD_BYTES = 1024 * 1024  # multipart framing and form fields


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    problems = settings.configuration_problems()
    if problems:
        raise RuntimeError(
            "Invalid configuration (copy .env.example to .env and fill it in):\n  - " + "\n  - ".join(problems)
        )
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    storage.ensure_storage_dirs()
    run_migrations()
    with SessionLocal() as db:
        storage.relocate_legacy_files(db, settings.upload_path, storage.get_file_store())
        sessions.purge_expired(db)
        audit.purge_old(db)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    # The interactive API docs are switched off: this is a private app with no public API consumers.
    app = FastAPI(
        title="Personal Medical Records",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=settings.max_upload_bytes + UPLOAD_OVERHEAD_BYTES)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.cookie_secure)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        # Log where it happened, never the query string or body (they can contain medical data).
        logger.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
        return JSONResponse({"detail": "Something went wrong on the server."}, status_code=500)

    for module in (health, auth, account, records, directories, documents, overview, backup, admin):
        app.include_router(module.router)

    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React app (history-API fallback to index.html)."""
    dist = FRONTEND_DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
        if full_path:
            try:
                candidate = (dist / full_path).resolve()
            except (OSError, ValueError):
                candidate = None
            if candidate and candidate.is_file() and candidate.is_relative_to(dist):
                cache = "public, max-age=31536000, immutable" if candidate.parent.name == "assets" else "no-cache"
                return FileResponse(candidate, headers={"Cache-Control": cache})
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="The web app has not been built yet. Run `npm run build` in the frontend folder.",
            )
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
