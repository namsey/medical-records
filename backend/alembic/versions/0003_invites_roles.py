"""invites and roles: users get a role and can be disabled; single-use invites

The ADMIN_EMAIL account becomes admin. Other existing accounts could not sign in before (only one email was
allowed), so they start disabled; an admin can enable them. Columns are added in place (no table copy).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-19 14:00:00.000000
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import get_settings


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('role', sa.String(length=16), nullable=False, server_default='user'))
    op.add_column('users', sa.Column('disabled_at', sa.DateTime(), nullable=True))

    connection = op.get_bind()
    admin_email = get_settings().admin_email_normalized
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')
    connection.execute(sa.text("UPDATE users SET role = 'admin' WHERE lower(email) = :email"), {'email': admin_email})
    connection.execute(
        sa.text('UPDATE users SET disabled_at = :now WHERE lower(email) != :email'), {'email': admin_email, 'now': now}
    )

    op.create_table('invites',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_by_id', sa.String(length=36), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('used_by_id', sa.String(length=36), nullable=True),
    sa.Column('revoked_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name='fk_invites_created_by_id_users', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['used_by_id'], ['users.id'], name='fk_invites_used_by_id_users', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash', name='uq_invites_token_hash')
    )
    with op.batch_alter_table('invites', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_invites_email'), ['email'], unique=False)


def downgrade() -> None:
    # Development only. Dropping the columns copies the users table: run with foreign keys off.
    with op.batch_alter_table('invites', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invites_email'))
    op.drop_table('invites')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('disabled_at')
        batch_op.drop_column('role')
