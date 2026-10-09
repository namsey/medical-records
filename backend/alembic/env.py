"""Alembic environment. The database URL always comes from the application settings."""

from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401  (register all tables on Base.metadata)
from app.config import get_settings
from app.database import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().resolved_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        get_settings().resolved_database_url,
        connect_args={"check_same_thread": False},
        hide_parameters=True,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
