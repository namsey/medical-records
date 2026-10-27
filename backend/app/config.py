"""Application settings, loaded from environment variables / the project-root `.env` file."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

MIN_SESSION_SECRET_LENGTH = 32
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    # The bootstrap admin. ALLOWED_EMAIL is the setting's old name and still works.
    admin_email: str = Field(default="", validation_alias=AliasChoices("admin_email", "allowed_email"))
    session_secret: str = ""
    database_url: str = "sqlite:///data/medical_records.db"
    files_dir: str = "data/files"
    upload_dir: str = "data/uploads"  # old layout, only read to move files into files_dir
    max_upload_size_mb: int = Field(default=20, ge=1, le=500)
    default_quota_mb: int = Field(default=100, ge=1, le=1_000_000)  # per account, unless the admin sets another
    clamav_socket: str = ""  # e.g. /run/clamav/clamd.ctl: scan every upload with ClamAV
    # Shown in the app as the contact for privacy questions and complaints (default: the admin's email).
    # Monitoring (#45): /api/health/disk fails above this, /api/health/backup reads backup.sh's status files.
    disk_alert_percent: int = Field(default=80, ge=1, le=100)
    backup_status_dir: str = ""  # e.g. /var/lib/medical-records-backup; empty: backups are not monitored
    backup_max_age_hours: int = Field(default=26, ge=1, le=24 * 30)
    grievance_name: str = ""
    grievance_email: str = ""
    session_max_age_days: int = Field(default=14, ge=1, le=365)
    session_idle_hours: int = Field(default=24, ge=1, le=720)
    # Containers (ctr-4). Proxies whose X-Forwarded-For is trusted for the client IP (comma-separated, or "*").
    forwarded_allow_ips: str = "127.0.0.1"
    # The disk checked as "system" by /api/health/disk; empty: only the data disk (inside a container).
    system_disk_path: str = "/"
    # On SIGTERM, requests still running (uploads) get this long to finish.
    shutdown_grace_seconds: int = Field(default=30, ge=0, le=600)
    # Set in the Docker image from the build (GET /api/version); "dev" when unset.
    app_commit: str = ""
    app_version: str = ""

    @property
    def admin_email_normalized(self) -> str:
        return self.admin_email.strip().lower()

    @property
    def public_origin(self) -> str:
        """The app's public address (scheme and host), taken from the OAuth redirect URI."""
        parts = urlsplit(self.google_redirect_uri.strip())
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def default_quota_bytes(self) -> int:
        return self.default_quota_mb * 1024 * 1024

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @staticmethod
    def _project_path(value: str) -> Path:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    @property
    def files_path(self) -> Path:
        return self._project_path(self.files_dir)

    @property
    def upload_path(self) -> Path:
        return self._project_path(self.upload_dir)

    @property
    def resolved_database_url(self) -> str:
        """Database URL where a relative SQLite path is anchored at the project root."""
        url = make_url(self.database_url)
        if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
            db_path = Path(url.database).expanduser()
            if not db_path.is_absolute():
                db_path = PROJECT_ROOT / db_path
            url = url.set(database=str(db_path))
        return url.render_as_string(hide_password=False)

    @property
    def sqlite_path(self) -> Path:
        url = make_url(self.resolved_database_url)
        if not url.drivername.startswith("sqlite") or not url.database:
            raise RuntimeError("DATABASE_URL must point to a SQLite file")
        return Path(url.database)

    @property
    def cookie_secure(self) -> bool:
        """Session cookies are marked Secure whenever the OAuth redirect URI is HTTPS."""
        return self.google_redirect_uri.strip().lower().startswith("https://")

    def configuration_problems(self) -> list[str]:
        problems: list[str] = []
        required = {
            "GOOGLE_CLIENT_ID": self.google_client_id,
            "GOOGLE_CLIENT_SECRET": self.google_client_secret,
            "GOOGLE_REDIRECT_URI": self.google_redirect_uri,
            "ADMIN_EMAIL": self.admin_email,
        }
        for name, value in required.items():
            if not value.strip():
                problems.append(f"{name} is not set")
        if len(self.session_secret) < MIN_SESSION_SECRET_LENGTH:
            problems.append(f"SESSION_SECRET must be set and at least {MIN_SESSION_SECRET_LENGTH} characters long")
        if "@" not in self.admin_email:
            problems.append("ADMIN_EMAIL must be an email address")
        redirect = urlsplit(self.google_redirect_uri.strip())
        if self.google_redirect_uri.strip() and not (
            redirect.scheme == "https" or (redirect.scheme == "http" and redirect.hostname in LOCAL_HOSTS)
        ):
            problems.append(
                "GOOGLE_REDIRECT_URI must use https:// (plain http:// only works for localhost), "
                "so session cookies are always Secure on a server"
            )
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
