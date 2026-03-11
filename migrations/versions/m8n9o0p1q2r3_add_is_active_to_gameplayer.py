"""add_is_active_to_gameplayer

Revision ID: m8n9o0p1q2r3
Revises: l7m8n9o0p1q2
Create Date: 2026-03-12 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision = 'm8n9o0p1q2r3'
down_revision = 'l7m8n9o0p1q2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('gameplayer')]
    if 'is_active' not in columns:
        op.add_column(
            'gameplayer',
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1')
        )
        connection.execute(sa.text("UPDATE gameplayer SET is_active = 1"))


def downgrade() -> None:
    op.drop_column('gameplayer', 'is_active')
