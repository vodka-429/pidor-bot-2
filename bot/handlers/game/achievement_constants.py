"""
Константы достижений для игры "Пидор дня".

Достижения хранятся как константы в коде, а не в БД.
Это упрощает схему и достаточно для MVP.
"""

from typing import Optional

# Словарь всех достижений
ACHIEVEMENTS = {
    "first_blood": {
        "name": "🩸 Первая кровь",
        "description": "Первая победа в чате",
        "reward": 10,
        "is_periodic": False,
        "period_type": None
    },
    "streak_3": {
        "name": "🎯 Снайпер",
        "description": "3 победы подряд",
        "reward": 20,
        "is_periodic": False,
        "period_type": None
    },
    "streak_5": {
        "name": "⚡ Серия 5",
        "description": "5 побед подряд",
        "reward": 30,
        "is_periodic": False,
        "period_type": None
    },
    "streak_7": {
        "name": "🌟 Серия 7",
        "description": "7 побед подряд",
        "reward": 50,
        "is_periodic": False,
        "period_type": None
    }
}


def get_achievement(code: str) -> Optional[dict]:
    """
    Получить достижение по коду.

    Args:
        code: Код достижения (ключ из словаря ACHIEVEMENTS)

    Returns:
        dict с данными достижения или None, если достижение не найдено
    """
    return ACHIEVEMENTS.get(code)
