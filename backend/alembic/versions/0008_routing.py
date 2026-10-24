"""Add route estimates and road blockages.

Revision ID: 0008_routing
Revises: 0007_user_organization
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_routing'
down_revision = '0007_user_organization'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'road_blockages',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('radius_km', sa.Float(), nullable=False),
        sa.Column('reported_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('verified', sa.Boolean(), nullable=False),
        sa.Column('reported_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('cleared_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.CheckConstraint('latitude BETWEEN -90 AND 90', name='ck_blockages_latitude_range'),
        sa.CheckConstraint('longitude BETWEEN -180 AND 180', name='ck_blockages_longitude_range'),
        sa.CheckConstraint('radius_km > 0 AND radius_km <= 5', name='ck_blockages_radius_range'),
    )
    op.create_table(
        'routes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('from_point', sa.JSON(), nullable=False),
        sa.Column('to_point', sa.JSON(), nullable=False),
        sa.Column('geometry', sa.JSON(), nullable=False),
        sa.Column('distance_km', sa.Float(), nullable=False),
        sa.Column('duration_min', sa.Float(), nullable=False),
        sa.Column('blocked_segments_considered', sa.JSON(), nullable=False),
        sa.Column('avoids_blockages', sa.Boolean(), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('engine', sa.String(length=30), nullable=False),
        sa.CheckConstraint('distance_km >= 0', name='ck_routes_nonnegative_distance'),
        sa.CheckConstraint('duration_min >= 0', name='ck_routes_nonnegative_duration'),
    )


def downgrade() -> None:
    op.drop_table('routes')
    op.drop_table('road_blockages')
