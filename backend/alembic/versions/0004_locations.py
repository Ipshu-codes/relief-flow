"""Add hierarchical locations.

Revision ID: 0004_locations
Revises: 0003_incidents
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_locations'
down_revision = '0003_incidents'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'locations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('location_type', sa.String(length=30), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('boundary', sa.JSON(), nullable=True),
        sa.Column('parent_location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=True),
        sa.Column('baseline_households_estimate', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            '(latitude IS NULL AND longitude IS NULL) OR '
            '(latitude IS NOT NULL AND longitude IS NOT NULL)',
            name='ck_locations_coordinate_pair',
        ),
        sa.CheckConstraint(
            'latitude IS NULL OR latitude BETWEEN -90 AND 90',
            name='ck_locations_latitude_range',
        ),
        sa.CheckConstraint(
            'longitude IS NULL OR longitude BETWEEN -180 AND 180',
            name='ck_locations_longitude_range',
        ),
        sa.CheckConstraint(
            'baseline_households_estimate IS NULL OR baseline_households_estimate >= 0',
            name='ck_locations_nonnegative_household_estimate',
        ),
    )


def downgrade() -> None:
    op.drop_table('locations')
