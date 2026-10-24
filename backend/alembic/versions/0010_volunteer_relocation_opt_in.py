"""Add volunteer relocation opt-in.

Revision ID: 0010_volunteer_relocation_opt_in
Revises: 0009_assignments
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_volunteer_relocation_opt_in'
down_revision = '0009_assignments'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'volunteer_profiles',
        sa.Column('willing_to_relocate', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('volunteer_profiles', 'willing_to_relocate')
