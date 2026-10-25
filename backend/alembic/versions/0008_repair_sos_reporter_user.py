"""Repair the reporter identity column on older SOS databases."""

from alembic import op
import sqlalchemy as sa

revision = '0008_repair_sos_reporter_user'
down_revision = '0007_incident_state_machine'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {
        column['name'] for column in sa.inspect(bind).get_columns('sos_events')
    }
    if 'reporter_user_id' not in columns:
        with op.batch_alter_table('sos_events', recreate='always') as batch_op:
            batch_op.add_column(
                sa.Column('reporter_user_id', sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                'fk_sos_events_reporter_user_id',
                'users',
                ['reporter_user_id'],
                ['id'],
            )


def downgrade():
    with op.batch_alter_table('sos_events', recreate='always') as batch_op:
        batch_op.drop_constraint(
            'fk_sos_events_reporter_user_id', type_='foreignkey'
        )
        batch_op.drop_column('reporter_user_id')
