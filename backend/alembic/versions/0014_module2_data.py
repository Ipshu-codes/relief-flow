"""Add Module 2 baselines, resources, confirmations, and bottlenecks.

Revision ID: 0014_module2_data
Revises: 0013_match_score_inputs
"""
from alembic import op
import sqlalchemy as sa

revision = '0014_module2_data'
down_revision = '0013_match_score_inputs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'raw_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('sender_ref', sa.String(length=160), nullable=True),
        sa.Column('client_uuid', sa.String(length=36), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('parse_status', sa.String(length=20), nullable=False),
        sa.Column('parsed_json', sa.JSON(), nullable=True),
        sa.CheckConstraint("channel IN ('app', 'sms', 'mesh', 'web')", name='ck_raw_reports_channel'),
        sa.UniqueConstraint('client_uuid', name='uq_raw_reports_client_uuid'),
    )
    op.create_table(
        'baseline_settlements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=False),
        sa.Column('estimated_households', sa.Integer(), nullable=False),
        sa.Column('estimated_population', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('data_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('location_id', name='uq_baseline_settlements_location'),
        sa.CheckConstraint('estimated_households >= 0', name='ck_baseline_households_nonnegative'),
        sa.CheckConstraint(
            'estimated_population IS NULL OR estimated_population >= 0',
            name='ck_baseline_population_nonnegative',
        ),
        sa.CheckConstraint('confidence BETWEEN 0 AND 1', name='ck_baseline_confidence_range'),
    )
    op.create_table(
        'baseline_features',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('feature_type', sa.String(length=60), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=True),
        sa.Column('geometry', sa.JSON(), nullable=False),
        sa.Column('source', sa.String(length=80), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'historical_incidents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('incident_type', sa.String(length=40), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=True),
        sa.Column('affected_area', sa.Text(), nullable=True),
        sa.Column('damage_summary', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=80), nullable=False),
    )
    op.create_table(
        'hazard_zones',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=True),
        sa.Column('geometry', sa.JSON(), nullable=False),
        sa.Column('hazard_type', sa.String(length=30), nullable=False),
        sa.Column('risk_level', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=80), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("hazard_type IN ('flood', 'landslide', 'other')", name='ck_hazard_zones_type'),
        sa.CheckConstraint('risk_level BETWEEN 1 AND 5', name='ck_hazard_zones_risk'),
    )
    op.create_table(
        'damage_assessments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('verified', sa.Boolean(), nullable=False),
        sa.Column('verified_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('damage_level', sa.Integer(), nullable=False),
        sa.Column('details', sa.Text(), nullable=False),
        sa.Column('evidence_ref', sa.String(length=300), nullable=True),
        sa.Column('assessed_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('pre', 'post')", name='ck_damage_assessments_kind'),
        sa.CheckConstraint('damage_level BETWEEN 0 AND 5', name='ck_damage_assessments_level'),
    )
    op.create_table(
        'resources',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('resource_type', sa.String(length=40), nullable=False),
        sa.Column('unit', sa.String(length=40), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
    )
    op.create_table(
        'resource_stock',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('resource_id', sa.Integer(), sa.ForeignKey('resources.id'), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=True),
        sa.Column('quantity_available', sa.Float(), nullable=False),
        sa.Column('quantity_reserved', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            'organization_id', 'resource_id', 'location_id',
            name='uq_resource_stock_source',
        ),
        sa.CheckConstraint('quantity_available >= 0', name='ck_resource_stock_available'),
        sa.CheckConstraint('quantity_reserved >= 0', name='ck_resource_stock_reserved'),
    )
    op.create_table(
        'resource_movements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('need_id', sa.Integer(), sa.ForeignKey('needs.id'), nullable=False),
        sa.Column('resource_id', sa.Integer(), sa.ForeignKey('resources.id'), nullable=False),
        sa.Column('stock_id', sa.Integer(), sa.ForeignKey('resource_stock.id'), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('quantity_confirmed', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('client_uuid', sa.String(length=36), nullable=True),
        sa.Column('allocated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('quantity > 0', name='ck_resource_movements_positive_quantity'),
        sa.CheckConstraint('quantity_confirmed >= 0', name='ck_resource_movements_confirmed_nonnegative'),
        sa.CheckConstraint('quantity_confirmed <= quantity', name='ck_resource_movements_confirmed_lte_quantity'),
        sa.CheckConstraint(
            "status IN ('allocated', 'dispatched', 'delivered', 'confirmed', 'cancelled')",
            name='ck_resource_movements_status',
        ),
        sa.UniqueConstraint('client_uuid', name='uq_resource_movements_client_uuid'),
    )
    op.create_table(
        'delivery_confirmations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('movement_id', sa.Integer(), sa.ForeignKey('resource_movements.id'), nullable=False),
        sa.Column('client_uuid', sa.String(length=36), nullable=False),
        sa.Column('confirmed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('quantity_received', sa.Float(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('full', 'partial', 'not_received')",
            name='ck_delivery_confirmations_status',
        ),
        sa.CheckConstraint('quantity_received >= 0', name='ck_delivery_confirmations_quantity'),
        sa.UniqueConstraint('client_uuid', name='uq_delivery_confirmations_client_uuid'),
    )
    op.create_table(
        'bottleneck_flags',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('flag_type', sa.String(length=60), nullable=False),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id'), nullable=True),
        sa.Column('need_id', sa.Integer(), sa.ForeignKey('needs.id'), nullable=True),
        sa.Column('severity', sa.Integer(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('suggested_action', sa.Text(), nullable=False),
        sa.CheckConstraint('severity BETWEEN 1 AND 5', name='ck_bottleneck_flags_severity'),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved')",
            name='ck_bottleneck_flags_status',
        ),
    )


def downgrade() -> None:
    op.drop_table('bottleneck_flags')
    op.drop_table('delivery_confirmations')
    op.drop_table('resource_movements')
    op.drop_table('resource_stock')
    op.drop_table('resources')
    op.drop_table('damage_assessments')
    op.drop_table('hazard_zones')
    op.drop_table('historical_incidents')
    op.drop_table('baseline_features')
    op.drop_table('baseline_settlements')
    op.drop_table('raw_reports')
