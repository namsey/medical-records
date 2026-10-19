"""record ownership: every record, doctor, laboratory and tag belongs to one user

Existing rows are assigned to the owner account (the ADMIN_EMAIL user, formerly ALLOWED_EMAIL), which is created if it has never
signed in. Tag names become unique per user instead of across the whole app.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-19 10:00:00.000000
"""
import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import get_settings


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWNED_TABLES = ('doctors', 'labs', 'tags', 'medical_records')
# The tags table from 0001 has an unnamed UNIQUE(name_key); this convention lets batch mode find and drop it.
TAG_NAMING = {'uq': 'uq_%(table_name)s_%(column_0_name)s'}


def _owner_id(connection) -> str | None:
    """The owner's user id, creating the user row if needed. None when there is nothing to assign."""
    has_rows = any(connection.execute(sa.text(f'SELECT 1 FROM {table} LIMIT 1')).first() for table in OWNED_TABLES)
    if not has_rows:
        return None
    email = get_settings().admin_email_normalized
    if '@' not in email:
        raise RuntimeError('ADMIN_EMAIL must be set to assign existing records to their owner')
    row = connection.execute(sa.text('SELECT id FROM users WHERE lower(email) = :email'), {'email': email}).first()
    if row:
        return row[0]
    owner_id = str(uuid.uuid4())
    connection.execute(
        sa.text('INSERT INTO users (id, email, name, created_at) VALUES (:id, :email, NULL, :now)'),
        {'id': owner_id, 'email': email, 'now': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')},
    )
    return owner_id


def upgrade() -> None:
    connection = op.get_bind()
    # Batch mode copies each table and drops the old one. With foreign keys on, that DROP would cascade and
    # delete documents, medicines, results and tag links, so refuse to run rather than lose records.
    if connection.execute(sa.text('PRAGMA foreign_keys')).scalar():
        raise RuntimeError('Run this migration with SQLite foreign keys switched off')

    owner_id = _owner_id(connection)
    for table in OWNED_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('user_id', sa.String(length=36), nullable=True))
        if owner_id:
            connection.execute(sa.text(f'UPDATE {table} SET user_id = :owner'), {'owner': owner_id})

    for table in ('doctors', 'labs'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('user_id', existing_type=sa.String(length=36), nullable=False)
            batch_op.create_foreign_key(f'fk_{table}_user_id_users', 'users', ['user_id'], ['id'], ondelete='CASCADE')
            batch_op.create_index(batch_op.f(f'ix_{table}_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('tags', schema=None, naming_convention=TAG_NAMING) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.String(length=36), nullable=False)
        batch_op.create_foreign_key('fk_tags_user_id_users', 'users', ['user_id'], ['id'], ondelete='CASCADE')
        batch_op.drop_constraint('uq_tags_name_key', type_='unique')
        batch_op.create_unique_constraint('uq_tags_user_id_name_key', ['user_id', 'name_key'])

    with op.batch_alter_table('medical_records', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.String(length=36), nullable=False)
        batch_op.create_foreign_key('fk_medical_records_user_id_users', 'users', ['user_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index('ix_medical_records_user_date', ['user_id', 'record_date', 'created_at'], unique=False)


def downgrade() -> None:
    # Development only: fails if two users have a tag with the same name.
    with op.batch_alter_table('medical_records', schema=None) as batch_op:
        batch_op.drop_index('ix_medical_records_user_date')
        batch_op.drop_constraint('fk_medical_records_user_id_users', type_='foreignkey')
        batch_op.drop_column('user_id')

    with op.batch_alter_table('tags', schema=None) as batch_op:
        batch_op.drop_constraint('uq_tags_user_id_name_key', type_='unique')
        batch_op.drop_constraint('fk_tags_user_id_users', type_='foreignkey')
        batch_op.drop_column('user_id')
        batch_op.create_unique_constraint('uq_tags_name_key', ['name_key'])

    for table in ('labs', 'doctors'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f'ix_{table}_user_id'))
            batch_op.drop_constraint(f'fk_{table}_user_id_users', type_='foreignkey')
            batch_op.drop_column('user_id')
