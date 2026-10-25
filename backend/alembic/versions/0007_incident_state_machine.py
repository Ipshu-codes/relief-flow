"""Add controlled incident state machine to the incidents table.

States: received -> acknowledged -> verified -> awaiting_dispatch ->
assigned -> responding -> on_scene -> resolved, with cancelled available
from any non-terminal state. Every transition is recorded in the shared
hash-linked audit_log.

Existing incidents with the legacy status 'active' are migrated to
'received' before the check constraint is added.
"""

from alembic import op
import sqlalchemy as sa


revision = '0007_incident_state_machine'
down_revision = '0006_sos_state_machine'
branch_labels = None
depends_on = None

STATES = (
    "'received', 'acknowledged', 'verified', 'awaiting_dispatch', "
    "'assigned', 'responding', 'on_scene', 'resolved', 'cancelled'"
)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Clean up any leftover temp table from a previous failed attempt.
    tables = inspector.get_table_names()
    if '_alembic_tmp_incidents' in tables:
        op.drop_table('_alembic_tmp_incidents')

    # Migrate legacy 'active' incidents to 'received' before constraining.
    columns = [c['name'] for c in inspector.get_columns('incidents')]
    if 'status' in columns:
        op.execute("UPDATE incidents SET status = 'received' WHERE status = 'active'")

    with op.batch_alter_table('incidents', recreate='always') as batch_op:
        constraints = [
            c['name']
            for c in inspector.get_check_constraints('incidents')
            if 'status' in (c.get('sqltext') or '')
        ]
        for name in constraints:
            batch_op.drop_constraint(name, type_='check')
        batch_op.create_check_constraint(
            'ck_incidents_status',
            f'status IN ({STATES})',
        )


def downgrade():
    raise RuntimeError('Restore a backup to avoid losing incident state history.')
