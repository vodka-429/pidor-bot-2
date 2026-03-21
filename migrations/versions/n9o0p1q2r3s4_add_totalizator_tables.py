"""add_totalizator_tables

Revision ID: n9o0p1q2r3s4
Revises: m8n9o0p1q2r3
Create Date: 2026-03-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision = 'n9o0p1q2r3s4'
down_revision = 'm8n9o0p1q2r3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('totalizator',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.AutoString(), nullable=False),
    sa.Column('stake', sa.Integer(), nullable=False),
    sa.Column('option_yes', sqlmodel.AutoString(), nullable=False, server_default='За'),
    sa.Column('option_no', sqlmodel.AutoString(), nullable=False, server_default='Против'),
    sa.Column('deadline_year', sa.Integer(), nullable=False),
    sa.Column('deadline_day', sa.Integer(), nullable=False),
    sa.Column('status', sqlmodel.AutoString(), nullable=False, server_default='open'),
    sa.Column('message_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['creator_id'], ['tguser.id'], ),
    sa.ForeignKeyConstraint(['game_id'], ['game.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('totalizatorbet',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('totalizator_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('choice', sqlmodel.AutoString(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['totalizator_id'], ['totalizator.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['tguser.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('totalizator_id', 'user_id', name='unique_totalizator_bet')
    )


def downgrade() -> None:
    op.drop_table('totalizatorbet')
    op.drop_table('totalizator')
