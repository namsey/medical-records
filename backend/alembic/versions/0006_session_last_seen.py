"""session idle timeout: when each login session was last used

Existing sessions count as used now, so nobody is signed out by the upgrade itself.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-19 21:00:00.000000
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite cannot add a column with a non-constant default, so add it empty, fill it, then make it required.
    op.add_column('sessions', sa.Column('last_seen_at', sa.DateTime(), nullable=True))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sessions = sa.table('sessions', sa.column('last_seen_at', sa.DateTime()))
    op.execute(sessions.update().values(last_seen_at=now))
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.alter_column('last_seen_at', existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_column('last_seen_at')
