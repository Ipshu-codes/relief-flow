"""Add community help offers and in-app notifications."""

from alembic import op
import sqlalchemy as sa

revision = '0004_help_offers_notifications'
down_revision = '0003_user_profiles'
branch_labels = None
depends_on = None


def upgrade():
    from app.db import Base
    from app import models  # noqa: F401

    Base.metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Restore a backup to avoid discarding community help history.')
