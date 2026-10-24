"""Add volunteer profiles, skills, and availability windows.

Revision ID: 0006_volunteers
Revises: 0005_needs_audit_log
"""
from alembic import op
import sqlalchemy as sa

revision = '0006_volunteers'
down_revision = '0005_needs_audit_log'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'volunteer_profiles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('base_location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=True),
        sa.Column('max_travel_km', sa.Float(), nullable=False),
        sa.Column('availability_status', sa.String(length=20), nullable=False),
        sa.Column('languages', sa.JSON(), nullable=False),
        sa.Column('equipment', sa.JSON(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('max_travel_km > 0', name='ck_volunteer_profiles_positive_travel'),
        sa.CheckConstraint(
            "availability_status IN ('available', 'assigned', 'unavailable', 'off_duty')",
            name='ck_volunteer_profiles_availability',
        ),
    )
    op.create_table(
        'skills',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=80), nullable=False, unique=True),
        sa.Column('category', sa.String(length=60), nullable=False),
    )
    op.create_table(
        'volunteer_skills',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('volunteer_id', sa.Integer(), sa.ForeignKey('volunteer_profiles.id'), nullable=False),
        sa.Column('skill_id', sa.Integer(), sa.ForeignKey('skills.id'), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('certification_name', sa.String(length=160), nullable=True),
        sa.Column('certificate_ref', sa.String(length=240), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=False),
        sa.Column('verified_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('volunteer_id', 'skill_id', name='uq_volunteer_skill'),
        sa.CheckConstraint('level BETWEEN 1 AND 5', name='ck_volunteer_skills_level'),
    )
    op.create_table(
        'availability_windows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('volunteer_id', sa.Integer(), sa.ForeignKey('volunteer_profiles.id'), nullable=False),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('ends_at > starts_at', name='ck_availability_window_order'),
    )


def downgrade() -> None:
    op.drop_table('availability_windows')
    op.drop_table('volunteer_skills')
    op.drop_table('skills')
    op.drop_table('volunteer_profiles')
