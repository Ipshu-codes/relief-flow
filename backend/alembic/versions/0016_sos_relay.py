"""Add offline SOS, gateways, batches, and acknowledgements.

Revision ID: 0016_sos_relay
Revises: 0015_raw_report_incident
"""
from alembic import op
import sqlalchemy as sa

revision = '0016_sos_relay'
down_revision = '0015_raw_report_incident'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'gateways',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('gateway_type', sa.String(length=20), nullable=False),
        sa.Column('api_key_hash', sa.String(length=64), nullable=False, unique=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.CheckConstraint("gateway_type IN ('meshtastic', 'sms', 'app')", name='ck_gateways_type'),
    )
    op.create_table(
        'sos_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_uuid', sa.String(length=36), nullable=False, unique=True),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('incidents.id'), nullable=True),
        sa.Column('sender_ref', sa.String(length=160), nullable=True),
        sa.Column('sender_verified', sa.Boolean(), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('location_accuracy_m', sa.Float(), nullable=True),
        sa.Column('has_location', sa.Boolean(), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('urgency', sa.Integer(), nullable=False),
        sa.Column('message', sa.String(length=500), nullable=False),
        sa.Column('created_at_device', sa.DateTime(timezone=True), nullable=True),
        sa.Column('received_at_server', sa.DateTime(timezone=True), nullable=False),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('relay_path', sa.JSON(), nullable=False),
        sa.Column('transmission_status', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('duplicate_of', sa.Integer(), sa.ForeignKey('sos_events.id'), nullable=True),
        sa.Column('linked_need_id', sa.Integer(), sa.ForeignKey('needs.id'), nullable=True),
        sa.Column('assignment_id', sa.Integer(), sa.ForeignKey('assignments.id'), nullable=True),
        sa.Column('gateway_id', sa.Integer(), sa.ForeignKey('gateways.id'), nullable=True),
        sa.Column('parsed_json', sa.JSON(), nullable=True),
        sa.CheckConstraint(
            "category IN ('FOOD', 'MEDICINE', 'TRAPPED', 'RESCUE', 'OTHER')",
            name='ck_sos_events_category',
        ),
        sa.CheckConstraint("channel IN ('app', 'mesh', 'sms', 'gateway')", name='ck_sos_events_channel'),
        sa.CheckConstraint(
            "status IN ('new', 'acknowledged', 'dispatched', 'resolved', 'false_alarm')",
            name='ck_sos_events_status',
        ),
        sa.CheckConstraint('urgency BETWEEN 1 AND 5', name='ck_sos_events_urgency'),
        sa.CheckConstraint('latitude IS NULL OR latitude BETWEEN -90 AND 90', name='ck_sos_events_latitude'),
        sa.CheckConstraint('longitude IS NULL OR longitude BETWEEN -180 AND 180', name='ck_sos_events_longitude'),
        sa.CheckConstraint(
            '(has_location = 0) OR (latitude IS NOT NULL AND longitude IS NOT NULL AND latitude != 0 AND longitude != 0)',
            name='ck_sos_events_location_honesty',
        ),
    )
    op.create_index('ix_sos_events_received_at_server', 'sos_events', ['received_at_server'])
    op.create_index('ix_sos_events_sender_received', 'sos_events', ['sender_ref', 'received_at_server'])
    op.create_table(
        'sync_batches',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('gateway_id', sa.Integer(), sa.ForeignKey('gateways.id'), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('count_received', sa.Integer(), nullable=False),
        sa.Column('count_new', sa.Integer(), nullable=False),
        sa.Column('count_duplicate', sa.Integer(), nullable=False),
        sa.Column('count_rejected', sa.Integer(), nullable=False),
        sa.CheckConstraint('count_received >= 0', name='ck_sync_batches_received'),
        sa.CheckConstraint('count_new >= 0', name='ck_sync_batches_new'),
        sa.CheckConstraint('count_duplicate >= 0', name='ck_sync_batches_duplicate'),
        sa.CheckConstraint('count_rejected >= 0', name='ck_sync_batches_rejected'),
    )
    op.create_table(
        'sos_acknowledgements',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sos_id', sa.Integer(), sa.ForeignKey('sos_events.id'), nullable=False),
        sa.Column('by_user', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('sos_acknowledgements')
    op.drop_table('sync_batches')
    op.drop_index('ix_sos_events_sender_received', table_name='sos_events')
    op.drop_index('ix_sos_events_received_at_server', table_name='sos_events')
    op.drop_table('sos_events')
    op.drop_table('gateways')
