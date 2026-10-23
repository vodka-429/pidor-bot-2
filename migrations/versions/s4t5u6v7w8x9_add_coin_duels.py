"""add coin duels and police calls

Revision ID: s4t5u6v7w8x9
Revises: r3s4t5u6v7w8
Create Date: 2026-10-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = 's4t5u6v7w8x9'
down_revision = 'r3s4t5u6v7w8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'coinduel',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('challenger_id', sa.Integer(), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('created_year', sa.Integer(), nullable=False),
        sa.Column('created_day', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('day', sa.Integer(), nullable=False),
        sa.Column('challenger_stake', sa.Integer(), nullable=False),
        sa.Column('target_stake', sa.Integer(), nullable=False),
        sa.Column('status', sqlmodel.AutoString(), nullable=False),
        sa.Column('challenger_roll', sa.Integer(), nullable=True),
        sa.Column('target_roll', sa.Integer(), nullable=True),
        sa.Column('tie_count', sa.Integer(), nullable=False),
        sa.Column('winner_id', sa.Integer(), nullable=True),
        sa.Column('commission', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['game_id'], ['game.id']),
        sa.ForeignKeyConstraint(['challenger_id'], ['tguser.id']),
        sa.ForeignKeyConstraint(['target_id'], ['tguser.id']),
        sa.ForeignKeyConstraint(['winner_id'], ['tguser.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('game_id', 'target_id', 'year', 'day', name='unique_coin_duel_target_day'),
        sa.UniqueConstraint(
            'game_id', 'challenger_id', 'created_year', 'created_day',
            name='unique_coin_duel_challenger_day',
        ),
    )
    op.create_index('ix_coinduel_game_day', 'coinduel', ['game_id', 'year', 'day'], unique=False)

    op.create_table(
        'policecall',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('caller_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('day', sa.Integer(), nullable=False),
        sa.Column('call_date', sa.Date(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('refunded_duels', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['game_id'], ['game.id']),
        sa.ForeignKeyConstraint(['caller_id'], ['tguser.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('game_id', 'year', 'day', name='unique_police_call_day'),
    )


def downgrade() -> None:
    op.drop_table('policecall')
    op.drop_index('ix_coinduel_game_day', table_name='coinduel')
    op.drop_table('coinduel')
