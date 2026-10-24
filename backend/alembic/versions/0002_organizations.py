"""Add organizations.

Revision ID: 0002_organizations
Revises: 0001_core_auth
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_organizations'
down_revision = '0001_core_auth'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'organizations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('organization_type', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('organizations')
