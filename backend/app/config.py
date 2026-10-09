"""Application settings, loaded from environment variables / the project-root `.env` file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

MIN_SESSION_SECRET_LENGTH = 32


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
    allowed_email: str = ""
    session_secret: str = ""
    database_url: str = "sqlite:///data/medical_records.db"
    upload_dir: str = "data/uploads"
    max_upload_size_mb: int = Field(default=20, ge=1, le=500)
    session_max_age_days: int = Field(default=14, ge=1, le=365)

    @property
    def allowed_email_normalized(self) -> str:
        return self.allowed_email.strip().lower()

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir).expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

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
            "ALLOWED_EMAIL": self.allowed_email,
        }
        for name, value in required.items():
            if not value.strip():
                problems.append(f"{name} is not set")
        if len(self.session_secret) < MIN_SESSION_SECRET_LENGTH:
            problems.append(f"SESSION_SECRET must be set and at least {MIN_SESSION_SECRET_LENGTH} characters long")
        if "@" not in self.allowed_email:
            problems.append("ALLOWED_EMAIL must be an email address")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()
