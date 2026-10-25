"""Expand SOS states for controlled coordination workflow."""

from alembic import op
import sqlalchemy as sa


revision = '0006_sos_state_machine'
down_revision = '0005_sos_severity_override'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    columns = {column['name'] for column in inspector.get_columns('sos_events')}
    if 'status' not in columns:
        return
    constraints = inspector.get_check_constraints('sos_events')
    with op.batch_alter_table('sos_events', recreate='always') as batch_op:
        if any(item.get('name') == 'ck_sos_events_status' for item in constraints):
            batch_op.drop_constraint('ck_sos_events_status', type_='check')
        batch_op.create_check_constraint(
            'ck_sos_events_status',
            "status IN ('new', 'received', 'acknowledged', 'verified', "
            "'awaiting_dispatch', 'assigned', 'responding', 'on_scene', "
            "'dispatched', 'resolved', 'cancelled', 'false_alarm')",
        )


def downgrade():
    raise RuntimeError('Restore a backup to avoid losing SOS state history.')
