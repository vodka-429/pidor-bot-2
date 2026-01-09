"""convert_immunity_to_year_day_and_remove_double_chance

Revision ID: 5b5e4dc83526
Revises: h3i4j5k6l7m8
Create Date: 2026-01-09 12:08:01.382400

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision = '5b5e4dc83526'
down_revision = 'h3i4j5k6l7m8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('gameplayereffect')]

    # Добавляем новые колонки для immunity, если их ещё нет
    if 'immunity_year' not in columns:
        op.add_column('gameplayereffect', sa.Column('immunity_year', sa.Integer(), nullable=True))
    if 'immunity_day' not in columns:
        op.add_column('gameplayereffect', sa.Column('immunity_day', sa.Integer(), nullable=True))

    # Конвертируем существующие данные immunity, если старая колонка ещё существует
    if 'immunity_until' in columns:
        # Определяем тип БД
        dialect_name = connection.dialect.name

        if dialect_name == 'postgresql':
            # PostgreSQL syntax
            connection.execute(sa.text("""
                UPDATE gameplayereffect
                SET immunity_year = EXTRACT(YEAR FROM immunity_until)::INTEGER,
                    immunity_day = EXTRACT(DOY FROM immunity_until)::INTEGER
                WHERE immunity_until IS NOT NULL
            """))
        elif dialect_name == 'sqlite':
            # SQLite syntax
            connection.execute(sa.text("""
                UPDATE gameplayereffect
                SET immunity_year = CAST(strftime('%Y', immunity_until) AS INTEGER),
                    immunity_day = CAST(strftime('%j', immunity_until) AS INTEGER)
                WHERE immunity_until IS NOT NULL
            """))

    # Удаляем старые колонки, если они ещё существуют
    if 'immunity_until' in columns:
        op.drop_column('gameplayereffect', 'immunity_until')
    if 'double_chance_until' in columns:
        op.drop_column('gameplayereffect', 'double_chance_until')
    if 'double_chance_bought_by' in columns:
        op.drop_column('gameplayereffect', 'double_chance_bought_by')


def downgrade() -> None:
    # Откат миграции
    op.add_column('gameplayereffect', sa.Column('immunity_until', sa.DateTime(), nullable=True))
    op.add_column('gameplayereffect', sa.Column('double_chance_until', sa.DateTime(), nullable=True))
    op.add_column('gameplayereffect', sa.Column('double_chance_bought_by', sa.Integer(), nullable=True))
    op.drop_column('gameplayereffect', 'immunity_day')
    op.drop_column('gameplayereffect', 'immunity_year')
