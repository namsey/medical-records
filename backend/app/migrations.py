"""Run Alembic migrations programmatically so the app always starts on an up-to-date schema."""

from alembic import command
from alembic.config import Config

from app.config import BACKEND_ROOT


def run_migrations() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")
