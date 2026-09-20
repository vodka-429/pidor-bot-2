"""add economy pilot features

Revision ID: q2r3s4t5u6v7
Revises: p1q2r3s4t5u6
Create Date: 2026-09-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = 'q2r3s4t5u6v7'
down_revision = 'p1q2r3s4t5u6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('gameplayer', sa.Column('custom_victory_phrase', sqlmodel.AutoString(), nullable=True))
    op.add_column('gameplayer', sa.Column('custom_victory_name_position', sqlmodel.AutoString(), nullable=True))
    op.add_column('gameplayer', sa.Column('telegram_title', sqlmodel.AutoString(), nullable=True))

    op.create_table(
        'coinrainpurchase',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('buyer_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('day', sa.Integer(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('recipient_amount', sa.Integer(), nullable=False),
        sa.Column('recipient_ids', sqlmodel.AutoString(), nullable=False),
        sa.Column('distributed_amount', sa.Integer(), nullable=False),
        sa.Column('bank_amount', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['buyer_id'], ['tguser.id']),
        sa.ForeignKeyConstraint(['game_id'], ['game.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('game_id', 'buyer_id', 'year', 'day', name='unique_coin_rain_buyer_day'),
    )
    op.create_index(
        'ix_coinrainpurchase_game_day',
        'coinrainpurchase',
        ['game_id', 'year', 'day'],
        unique=False,
    )

    op.create_table(
        'changelogreceipt',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('game_id', sa.Integer(), nullable=False),
        sa.Column('release_id', sqlmodel.AutoString(), nullable=False),
        sa.Column('shown_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['game_id'], ['game.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('game_id', 'release_id', name='unique_changelog_receipt'),
    )


def downgrade() -> None:
    op.drop_table('changelogreceipt')
    op.drop_index('ix_coinrainpurchase_game_day', table_name='coinrainpurchase')
    op.drop_table('coinrainpurchase')
    op.drop_column('gameplayer', 'telegram_title')
    op.drop_column('gameplayer', 'custom_victory_name_position')
    op.drop_column('gameplayer', 'custom_victory_phrase')
