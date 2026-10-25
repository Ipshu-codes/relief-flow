"""Preserve written SOS addresses and later GPS observations."""

from alembic import op
import sqlalchemy as sa

revision = '0002_sos_address'
down_revision = '0001_unified_schema'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('sos_events')}
    if 'address' not in columns:
        op.add_column('sos_events', sa.Column('address', sa.JSON(), nullable=True))
    if 'location_updated_at' not in columns:
        op.add_column('sos_events', sa.Column('location_updated_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError('Restore a backup to downgrade without discarding written SOS locations.')
