"""add coin deposits and duel deposit arrest

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9
Create Date: 2026-10-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = 't5u6v7w8x9y0'
down_revision = 's4t5u6v7w8x9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'coindeposit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('initial_amount', sa.Integer(), nullable=False),
        sa.Column('rate_bp', sa.Integer(), nullable=False),
        sa.Column('term_days', sa.Integer(), nullable=False),
        sa.Column('interest', sa.Integer(), nullable=False),
        sa.Column('opened_date', sa.Date(), nullable=False),
        sa.Column('matures_on', sa.Date(), nullable=False),
        sa.Column('status', sqlmodel.AutoString(), nullable=False),
        sa.Column('paid_interest', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['game.id']),
        sa.ForeignKeyConstraint(['user_id'], ['tguser.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_coindeposit_game_status', 'coindeposit', ['game_id', 'status', 'matures_on'], unique=False,
    )
    op.create_index(
        'unique_open_coin_deposit', 'coindeposit', ['game_id', 'user_id'], unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )

    op.add_column('coinduel', sa.Column('target_deposit_id', sa.Integer(), nullable=True))
    op.add_column(
        'coinduel',
        sa.Column('target_deposit_part', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_foreign_key(
        'fk_coinduel_target_deposit', 'coinduel', 'coindeposit', ['target_deposit_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_coinduel_target_deposit', 'coinduel', type_='foreignkey')
    op.drop_column('coinduel', 'target_deposit_part')
    op.drop_column('coinduel', 'target_deposit_id')
    op.drop_index('unique_open_coin_deposit', table_name='coindeposit')
    op.drop_index('ix_coindeposit_game_status', table_name='coindeposit')
    op.drop_table('coindeposit')
