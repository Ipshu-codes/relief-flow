"""Add assignments.

Revision ID: 0009_assignments
Revises: 0008_routing
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_assignments'
down_revision = '0008_routing'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'assignments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('need_id', sa.Integer(), sa.ForeignKey('needs.id'), nullable=False),
        sa.Column('volunteer_id', sa.Integer(), sa.ForeignKey('volunteer_profiles.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('proposed_by', sa.String(length=20), nullable=False),
        sa.Column('route_id', sa.Integer(), sa.ForeignKey('routes.id'), nullable=True),
        sa.Column('eta', sa.DateTime(timezone=True), nullable=True),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('outcome_notes', sa.Text(), nullable=True),
        sa.Column('completion_criteria_met', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'accepted', 'en_route', 'on_site', 'completed', 'cancelled', 'rejected')",
            name='ck_assignments_status',
        ),
        sa.CheckConstraint("proposed_by IN ('ai', 'coordinator')", name='ck_assignments_proposed_by'),
        sa.CheckConstraint(
            'starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at',
            name='ck_assignments_task_window_order',
        ),
    )


def downgrade() -> None:
    op.drop_table('assignments')
