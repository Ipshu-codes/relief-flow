"""Add AI call telemetry.

Revision ID: 0011_ai_call_log
Revises: 0010_volunteer_relocation_opt_in
"""
from alembic import op
import sqlalchemy as sa

revision = '0011_ai_call_log'
down_revision = '0010_volunteer_relocation_opt_in'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_call_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task', sa.String(length=80), nullable=False),
        sa.Column('prompt_version', sa.String(length=80), nullable=False),
        sa.Column('model', sa.String(length=120), nullable=False),
        sa.Column('latency_ms', sa.Integer(), nullable=False),
        sa.Column('input_summary', sa.Text(), nullable=False),
        sa.Column('output', sa.Text(), nullable=False),
        sa.Column('validation_result', sa.String(length=300), nullable=False),
        sa.Column('fallback_used', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('ai_call_log')
