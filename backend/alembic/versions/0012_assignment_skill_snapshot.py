"""Store validated skills on assignment proposals.

Revision ID: 0012_assignment_skill_snapshot
Revises: 0011_ai_call_log
"""
from alembic import op
import sqlalchemy as sa

revision = '0012_assignment_skill_snapshot'
down_revision = '0011_ai_call_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'assignments',
        sa.Column('required_skills_snapshot', sa.JSON(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('assignments', 'required_skills_snapshot')
