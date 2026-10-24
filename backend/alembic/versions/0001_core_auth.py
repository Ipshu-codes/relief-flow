"""Create the user table and baseline existing contribution tables.

Revision ID: 0001_core_auth
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_core_auth'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('contributions'):
        op.create_table(
            'contributions',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('donor_name', sa.String(length=120), nullable=False),
            sa.Column('is_anonymous', sa.Boolean(), nullable=False),
            sa.Column('amount_npr', sa.Float(), nullable=True),
            sa.Column('txn_id', sa.String(length=80), nullable=True, unique=True),
            sa.Column('channel', sa.String(length=30), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.Column('slip_path', sa.String(length=300), nullable=True),
            sa.Column('review_note', sa.Text(), nullable=True),
            sa.Column('receipt_token', sa.String(length=40), nullable=False, unique=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        )

    if not inspector.has_table('ledger_entries'):
        op.create_table(
            'ledger_entries',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('contribution_id', sa.Integer(), nullable=False),
            sa.Column('prev_hash', sa.String(length=64), nullable=False),
            sa.Column('entry_hash', sa.String(length=64), nullable=False),
            sa.Column('record_json', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )

    if not inspector.has_table('users'):
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('email', sa.String(length=254), nullable=False, unique=True),
            sa.Column('full_name', sa.String(length=120), nullable=False),
            sa.Column('password_hash', sa.String(length=512), nullable=False),
            sa.Column('role', sa.String(length=30), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index('ix_users_email', 'users', ['email'], unique=False)


def downgrade() -> None:
    pass
