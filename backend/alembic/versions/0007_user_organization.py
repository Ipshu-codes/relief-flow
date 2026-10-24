"""Associate users with an organization for org-scoped permissions.

Revision ID: 0007_user_organization
Revises: 0006_volunteers
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_user_organization'
down_revision = '0006_volunteers'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('organization_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_users_organization_id_organizations',
            'organizations',
            ['organization_id'],
            ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_constraint('fk_users_organization_id_organizations', type_='foreignkey')
        batch_op.drop_column('organization_id')
