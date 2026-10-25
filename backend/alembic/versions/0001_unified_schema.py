"""Adopt existing module tables or initialize a clean database without discarding data."""

from alembic import op
import sqlalchemy as sa

from app.db import Base
from app import models

revision = '0001_unified_schema'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    Base.metadata.create_all(bind, checkfirst=True)
    columns = {column['name'] for column in sa.inspect(bind).get_columns('volunteer_profiles')}
    if 'contact_info' not in columns:
        op.add_column('volunteer_profiles', sa.Column('contact_info', sa.String(240), nullable=True))


def downgrade():
    raise RuntimeError('This data-preserving adoption migration cannot be safely downgraded. Restore a backup.')
