"""consent and audit log: the privacy notice version each account agreed to, and an audit log of account events

Existing accounts have not agreed to the notice yet, so everyone (the admin too) is asked once.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-19 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('consent_version', sa.String(length=32), nullable=True))
    op.add_column('users', sa.Column('consented_at', sa.DateTime(), nullable=True))
    op.create_table('audit_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('at', sa.DateTime(), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False),
    sa.Column('actor_id', sa.String(length=36), nullable=True),
    sa.Column('actor_email', sa.String(length=320), nullable=True),
    sa.Column('target_id', sa.String(length=36), nullable=True),
    sa.Column('target_email', sa.String(length=320), nullable=True),
    sa.Column('detail', sa.String(length=100), nullable=True),
    sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name='fk_audit_events_actor_id_users', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['target_id'], ['users.id'], name='fk_audit_events_target_id_users', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_audit_events_at'), ['at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_audit_events_at'))
    op.drop_table('audit_events')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('consented_at')
        batch_op.drop_column('consent_version')
