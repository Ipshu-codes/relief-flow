"""Add core needs and shared audit log.

Revision ID: 0005_needs_audit_log
Revises: 0004_locations
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_needs_audit_log'
down_revision = '0004_locations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'needs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('incidents.id'), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=False),
        sa.Column('category', sa.String(length=30), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('required_skills', sa.JSON(), nullable=False),
        sa.Column('quantity_requested', sa.Float(), nullable=False),
        sa.Column('quantity_fulfilled', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(length=40), nullable=False),
        sa.Column('urgency', sa.Integer(), nullable=False),
        sa.Column('vulnerable_groups', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('verification_status', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('source_report_id', sa.Integer(), nullable=True),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('rescue', 'medical', 'water', 'food', 'shelter', 'technical_repair', 'other')",
            name='ck_needs_category',
        ),
        sa.CheckConstraint('quantity_requested >= 0', name='ck_needs_requested_nonnegative'),
        sa.CheckConstraint('quantity_fulfilled >= 0', name='ck_needs_fulfilled_nonnegative'),
        sa.CheckConstraint('quantity_fulfilled <= quantity_requested', name='ck_needs_fulfilled_lte_requested'),
        sa.CheckConstraint('urgency BETWEEN 1 AND 5', name='ck_needs_urgency_range'),
        sa.CheckConstraint(
            "status IN ('open', 'partially_fulfilled', 'in_progress', 'fulfilled', 'closed')",
            name='ck_needs_status',
        ),
        sa.CheckConstraint(
            "verification_status IN ('unverified', 'verified', 'rejected')",
            name='ck_needs_verification_status',
        ),
        sa.CheckConstraint(
            "source IN ('sos', 'report', 'volunteer', 'coordinator')",
            name='ck_needs_source',
        ),
    )
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('entity', sa.String(length=80), nullable=False),
        sa.Column('entity_id', sa.String(length=80), nullable=False),
        sa.Column('before_json', sa.Text(), nullable=True),
        sa.Column('after_json', sa.Text(), nullable=True),
        sa.Column('record_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('prev_hash', sa.String(length=64), nullable=False),
        sa.Column('entry_hash', sa.String(length=64), nullable=False),
        sa.UniqueConstraint('entry_hash', name='uq_audit_log_entry_hash'),
    )


def downgrade() -> None:
    op.drop_table('audit_log')
    op.drop_table('needs')
