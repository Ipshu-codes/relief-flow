"""Associate raw reports with incidents.

Revision ID: 0015_raw_report_incident
Revises: 0014_module2_data
"""
from alembic import op
import sqlalchemy as sa

revision = '0015_raw_report_incident'
down_revision = '0014_module2_data'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('raw_reports') as batch_op:
        batch_op.add_column(sa.Column('incident_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_raw_reports_incident_id_incidents',
            'incidents',
            ['incident_id'],
            ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('raw_reports') as batch_op:
        batch_op.drop_constraint('fk_raw_reports_incident_id_incidents', type_='foreignkey')
        batch_op.drop_column('incident_id')
