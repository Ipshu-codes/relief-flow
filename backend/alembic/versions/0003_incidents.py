"""Add incidents.

Revision ID: 0003_incidents
Revises: 0002_organizations
"""
from alembic import op
import sqlalchemy as sa

revision = '0003_incidents'
down_revision = '0002_organizations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'incidents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('incident_type', sa.String(length=40), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('affected_area', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('incidents')
