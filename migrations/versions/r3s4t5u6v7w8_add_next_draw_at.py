"""Add a persistent opening time for the next daily draw.

Revision ID: r3s4t5u6v7w8
Revises: q2r3s4t5u6v7
"""
from alembic import op
import sqlalchemy as sa


revision = "r3s4t5u6v7w8"
down_revision = "q2r3s4t5u6v7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("game", sa.Column("next_draw_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("game", "next_draw_at")
