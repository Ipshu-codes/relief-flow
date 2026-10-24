"""Add M1 match score inputs.

Revision ID: 0013_match_score_inputs
Revises: 0012_assignment_skill_snapshot
"""
from alembic import op
import sqlalchemy as sa

revision = '0013_match_score_inputs'
down_revision = '0012_assignment_skill_snapshot'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('organizations') as batch_op:
        batch_op.add_column(
            sa.Column('trust_score', sa.Float(), nullable=False, server_default='0.5')
        )
        batch_op.create_check_constraint(
            'ck_organizations_trust_score',
            'trust_score BETWEEN 0 AND 1',
        )
    with op.batch_alter_table('needs') as batch_op:
        batch_op.add_column(
            sa.Column('required_equipment', sa.JSON(), nullable=False, server_default='[]')
        )
        batch_op.add_column(
            sa.Column('preferred_languages', sa.JSON(), nullable=False, server_default='[]')
        )


def downgrade() -> None:
    with op.batch_alter_table('needs') as batch_op:
        batch_op.drop_column('preferred_languages')
        batch_op.drop_column('required_equipment')
    with op.batch_alter_table('organizations') as batch_op:
        batch_op.drop_constraint('ck_organizations_trust_score', type_='check')
        batch_op.drop_column('trust_score')
