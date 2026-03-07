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
    "streak_2": {
        "name": "🎯 Снайпер",
        "description": "2 победы подряд",
        "reward": 15,
        "is_periodic": False,
        "period_type": None
    },
    "streak_3": {
        "name": "⚡ Серия 3",
        "description": "3 победы подряд",
        "reward": 25,
        "is_periodic": False,
        "period_type": None
    },
    "streak_5": {
        "name": "🌟 Легенда",
        "description": "5 побед подряд",
        "reward": 50,
        "is_periodic": False,
        "period_type": None
    },
    "monthly_king": {
        "name": "👑 Король месяца",
        "description": "Больше всех побед за месяц",
        "reward": 30,
        "is_periodic": True,
        "period_type": "monthly"
    },
    "monthly_initiator": {
        "name": "🎯 Инициатор месяца",
        "description": "Больше всех запусков /pidor за месяц",
        "reward": 15,
        "is_periodic": True,
        "period_type": "monthly"
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
