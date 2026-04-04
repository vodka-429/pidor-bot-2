"""add_immunity_buyer_id_to_gameplayereffect

Revision ID: o0p1q2r3s4t5
Revises: n9o0p1q2r3s4
Create Date: 2026-04-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'o0p1q2r3s4t5'
down_revision = 'n9o0p1q2r3s4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('gameplayereffect', sa.Column('immunity_buyer_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('gameplayereffect', 'immunity_buyer_id')
