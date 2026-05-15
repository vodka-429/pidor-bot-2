"""add_birthday_to_tguser

Revision ID: p1q2r3s4t5u6
Revises: o0p1q2r3s4t5
Create Date: 2026-05-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p1q2r3s4t5u6'
down_revision = 'o0p1q2r3s4t5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('tguser')]

    if 'birth_month' not in columns:
        op.add_column('tguser', sa.Column('birth_month', sa.Integer(), nullable=True))
    if 'birth_day' not in columns:
        op.add_column('tguser', sa.Column('birth_day', sa.Integer(), nullable=True))

    # Бэкфилл ДР производится отдельным шагом — scripts/apply_birthdays.py
    # читает приватный birthdays.local.json и проставляет UPDATE.
    # Сделано так, чтобы tg_id живых людей не попадали в git.


def downgrade() -> None:
    op.drop_column('tguser', 'birth_day')
    op.drop_column('tguser', 'birth_month')
