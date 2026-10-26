"""Allow community offers to target a specific open need."""

from alembic import op
import sqlalchemy as sa

revision = '0009_targeted_help_offers'
down_revision = '0008_repair_sos_reporter_user'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column['name'] for column in inspector.get_columns('help_offers')}
    indexes = {index['name'] for index in inspector.get_indexes('help_offers')}
    foreign_keys = inspector.get_foreign_keys('help_offers')
    has_need_fk = any(
        foreign_key.get('constrained_columns') == ['need_id']
        and foreign_key.get('referred_table') == 'needs'
        for foreign_key in foreign_keys
    )

    with op.batch_alter_table('help_offers') as batch_op:
        if 'need_id' not in columns:
            batch_op.add_column(sa.Column('need_id', sa.Integer(), nullable=True))
        if not has_need_fk:
            batch_op.create_foreign_key(
                'fk_help_offers_need_id_needs', 'needs', ['need_id'], ['id']
            )
        if 'ix_help_offers_need_id' not in indexes:
            batch_op.create_index('ix_help_offers_need_id', ['need_id'])


def downgrade():
    bind = op.get_bind()
    columns = {
        column['name'] for column in sa.inspect(bind).get_columns('help_offers')
    }
    if 'need_id' not in columns:
        return
    indexes = {index['name'] for index in sa.inspect(bind).get_indexes('help_offers')}
    foreign_keys = sa.inspect(bind).get_foreign_keys('help_offers')
    need_fks = [
        fk for fk in foreign_keys
        if fk.get('constrained_columns') == ['need_id']
        and fk.get('referred_table') == 'needs'
    ]
    with op.batch_alter_table('help_offers') as batch_op:
        if 'ix_help_offers_need_id' in indexes:
            batch_op.drop_index('ix_help_offers_need_id')
        for foreign_key in need_fks:
            if foreign_key.get('name'):
                batch_op.drop_constraint(
                    foreign_key['name'], type_='foreignkey'
                )
        batch_op.drop_column('need_id')
