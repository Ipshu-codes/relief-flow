"""Add private user location and emergency-contact profiles."""

from alembic import op
import sqlalchemy as sa

revision = '0003_user_profiles'
down_revision = '0002_sos_address'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column['name'] for column in sa.inspect(bind).get_columns('users')}
    additions = [
        ('phone_number', sa.String(40)),
        ('address', sa.JSON()),
        ('latitude', sa.Float()),
        ('longitude', sa.Float()),
        ('location_accuracy_m', sa.Float()),
        ('emergency_contacts', sa.JSON()),
        ('profile_notes', sa.Text()),
    ]
    for name, column in additions:
        if name not in columns:
            op.add_column('users', sa.Column(name, column, nullable=True))


def downgrade():
    raise RuntimeError('Restore a backup to downgrade without discarding private profiles.')
