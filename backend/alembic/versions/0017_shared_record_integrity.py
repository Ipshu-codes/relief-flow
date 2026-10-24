"""Normalize shared report and need references.

Revision ID: 0017_shared_record_integrity
Revises: 0016_sos_relay
"""
import json

from alembic import op
import sqlalchemy as sa


revision = '0017_shared_record_integrity'
down_revision = '0016_sos_relay'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    orphaned_reports = connection.execute(sa.text(
        "SELECT COUNT(*) FROM needs n LEFT JOIN raw_reports r "
        "ON r.id = n.source_report_id "
        "WHERE n.source_report_id IS NOT NULL AND r.id IS NULL"
    )).scalar_one()
    if orphaned_reports:
        raise RuntimeError(
            f'Cannot add needs.source_report_id foreign key: {orphaned_reports} orphaned references found'
        )

    with op.batch_alter_table('needs') as batch_op:
        batch_op.add_column(
            sa.Column('confidence', sa.String(length=10), nullable=False, server_default='low')
        )
        batch_op.add_column(sa.Column('priority_rank', sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            'ck_needs_confidence', "confidence IN ('low', 'medium', 'high')"
        )
        batch_op.create_check_constraint(
            'ck_needs_priority_rank_positive',
            'priority_rank IS NULL OR priority_rank >= 1',
        )
        batch_op.create_foreign_key(
            'fk_needs_source_report_id_raw_reports',
            'raw_reports',
            ['source_report_id'],
            ['id'],
            ondelete='RESTRICT',
        )

    with op.batch_alter_table('raw_reports') as batch_op:
        batch_op.add_column(sa.Column('location_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_raw_reports_location_id_locations',
            'locations',
            ['location_id'],
            ['id'],
            ondelete='SET NULL',
        )

    raw_reports = sa.table(
        'raw_reports',
        sa.column('id', sa.Integer()),
        sa.column('parsed_json', sa.JSON()),
        sa.column('location_id', sa.Integer()),
    )
    locations = sa.table('locations', sa.column('id', sa.Integer()))
    needs = sa.table(
        'needs',
        sa.column('id', sa.Integer()),
        sa.column('source_report_id', sa.Integer()),
        sa.column('confidence', sa.String(length=10)),
    )
    valid_location_ids = set(connection.execute(sa.select(locations.c.id)).scalars())
    parsed_by_report = {}
    for report_id, parsed_json in connection.execute(
        sa.select(raw_reports.c.id, raw_reports.c.parsed_json)
    ):
        if isinstance(parsed_json, str):
            try:
                parsed_json = json.loads(parsed_json)
            except ValueError:
                parsed_json = None
        location_id = parsed_json.get('location_id') if isinstance(parsed_json, dict) else None
        if isinstance(location_id, int) and location_id in valid_location_ids:
            connection.execute(
                raw_reports.update()
                .where(raw_reports.c.id == report_id)
                .values(location_id=location_id)
            )
        parsed_by_report[report_id] = parsed_json

    for need_id, report_id in connection.execute(
        sa.select(needs.c.id, needs.c.source_report_id).where(needs.c.source_report_id.is_not(None))
    ):
        report_data = parsed_by_report.get(report_id)
        confidence = report_data.get('confidence') if isinstance(report_data, dict) else None
        if confidence in {'low', 'medium', 'high'}:
            connection.execute(
                needs.update().where(needs.c.id == need_id).values(confidence=confidence)
            )

    op.create_table(
        'ai_proposals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('incident_id', sa.Integer(), sa.ForeignKey('incidents.id'), nullable=False),
        sa.Column('batch_uuid', sa.String(length=36), nullable=False),
        sa.Column('candidate_key', sa.String(length=160), nullable=False),
        sa.Column('proposal_type', sa.String(length=30), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('confidence', sa.String(length=10), nullable=False),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('reviewed_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_entity', sa.String(length=80), nullable=True),
        sa.Column('result_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('batch_uuid', 'candidate_key', name='uq_ai_proposal_batch_candidate'),
        sa.CheckConstraint(
            "proposal_type IN ('assignment', 'reassignment', 'allocation', 'bottleneck_flag', 'priority')",
            name='ck_ai_proposals_type',
        ),
        sa.CheckConstraint("status IN ('proposed', 'approved', 'rejected')", name='ck_ai_proposals_status'),
        sa.CheckConstraint("source IN ('ai', 'fallback')", name='ck_ai_proposals_source'),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')",
            name='ck_ai_proposals_confidence',
        ),
    )
    op.create_index('ix_ai_proposals_incident_status', 'ai_proposals', ['incident_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_ai_proposals_incident_status', table_name='ai_proposals')
    op.drop_table('ai_proposals')
    with op.batch_alter_table('raw_reports') as batch_op:
        batch_op.drop_constraint('fk_raw_reports_location_id_locations', type_='foreignkey')
        batch_op.drop_column('location_id')

    with op.batch_alter_table('needs') as batch_op:
        batch_op.drop_constraint('fk_needs_source_report_id_raw_reports', type_='foreignkey')
        batch_op.drop_constraint('ck_needs_priority_rank_positive', type_='check')
        batch_op.drop_constraint('ck_needs_confidence', type_='check')
        batch_op.drop_column('priority_rank')
        batch_op.drop_column('confidence')