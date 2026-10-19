"""user quota: an optional per-account storage limit (empty means the DEFAULT_QUOTA_MB setting)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-19 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing accounts keep an empty limit, so they get the default.
    op.add_column('users', sa.Column('quota_bytes', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('quota_bytes')
