"""Preserve whether SOS severity was selected by the sender."""

from alembic import op
import sqlalchemy as sa

revision = '0005_sos_severity_override'
down_revision = '0004_help_offers_notifications'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('sos_events')}
    if 'urgency_override' not in columns:
        op.add_column(
            'sos_events',
            sa.Column('urgency_override', sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if 'reporter_user_id' not in columns:
        with op.batch_alter_table('sos_events', recreate='always') as batch_op:
            batch_op.add_column(sa.Column('reporter_user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                'fk_sos_events_reporter_user_id',
                'users',
                ['reporter_user_id'],
                ['id'],
            )


def downgrade():
    raise RuntimeError('Restore a backup to avoid losing sender-selected SOS severity.')
