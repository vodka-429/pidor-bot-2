"""Service functions for achievements system."""
import logging
from typing import List, Optional
from datetime import datetime

from sqlmodel import select

from bot.app.models import UserAchievement, GameResult, TGUser
from bot.handlers.game.achievement_constants import ACHIEVEMENTS, get_achievement
from bot.handlers.game.coin_service import add_coins
from bot.handlers.game.config import get_config_by_game_id
from bot.handlers.game.shop_service import is_leap_year, get_days_in_year

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


def has_achievement(
    db_session,
    game_id: int,
    user_id: int,
    achievement_code: str,
    year: int = None,
    period: int = None
) -> bool:
    """
    Проверить, есть ли у пользователя достижение.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        achievement_code: Код достижения (ключ из словаря ACHIEVEMENTS)
        year: Год получения (для периодических достижений)
        period: Номер периода (для периодических достижений)

    Returns:
        True если достижение есть, False если нет
    """
    stmt = select(UserAchievement).where(
        UserAchievement.game_id == game_id,
        UserAchievement.user_id == user_id,
        UserAchievement.achievement_code == achievement_code
    )

    # Для периодических достижений проверяем год и период
    if year is not None:
        stmt = stmt.where(UserAchievement.year == year)
    if period is not None:
        stmt = stmt.where(UserAchievement.period == period)

    achievement = db_session.exec(stmt).first()
    return achievement is not None


def award_achievement(
    db_session,
    game_id: int,
    user_id: int,
    achievement_code: str,
    year: int,
    period: int = None
) -> Optional[UserAchievement]:
    """
    Выдать достижение и начислить койны.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        achievement_code: Код достижения (ключ из словаря ACHIEVEMENTS)
        year: Год получения
        period: Номер периода (для периодических достижений, None для разовых)

    Returns:
        Созданное достижение UserAchievement или None если достижение уже есть
    """
    # Проверяем, что достижение существует
    achievement_data = get_achievement(achievement_code)
    if not achievement_data:
        logger.error(f"Achievement {achievement_code} not found in ACHIEVEMENTS")
        return None

    # Проверяем, нет ли уже такого достижения
    if has_achievement(db_session, game_id, user_id, achievement_code, year, period):
        logger.info(f"User {user_id} already has achievement {achievement_code}")
        return None

    # Создаём запись о достижении
    user_achievement = UserAchievement(
        game_id=game_id,
        user_id=user_id,
        achievement_code=achievement_code,
        year=year,
        period=period,
        earned_at=datetime.utcnow()
    )

    db_session.add(user_achievement)

    # Начисляем койны за достижение (без комиссии)
    reward = achievement_data['reward']
    add_coins(
        db_session,
        game_id,
        user_id,
        reward,
        year,
        f"achievement_{achievement_code}",
        auto_commit=False
    )

    logger.info(
        f"Awarded achievement {achievement_code} to user {user_id} in game {game_id}, "
        f"reward: {reward} coins"
    )

    return user_achievement


def get_user_achievements(
    db_session,
    game_id: int,
    user_id: int
) -> List[UserAchievement]:
    """
    Получить все достижения пользователя.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя

    Returns:
        Список достижений пользователя
    """
    stmt = select(UserAchievement).where(
        UserAchievement.game_id == game_id,
        UserAchievement.user_id == user_id
    ).order_by(UserAchievement.earned_at.desc())

    achievements = db_session.exec(stmt).all()
    logger.debug(f"Found {len(achievements)} achievements for user {user_id} in game {game_id}")
    return achievements


def get_current_win_streak(
    db_session,
    game_id: int,
    user_id: int
) -> int:
    """
    Получить текущую серию побед пользователя.

    Серия считается по последовательным дням с победами.
    Если игрок пропустил день — серия сбрасывается.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя

    Returns:
        Количество побед подряд
    """
    # Получаем все победы пользователя, отсортированные по году и дню (по убыванию)
    stmt = select(GameResult).where(
        GameResult.game_id == game_id,
        GameResult.winner_id == user_id
    ).order_by(GameResult.year.desc(), GameResult.day.desc())

    results = db_session.exec(stmt).all()

    if not results:
        return 0

    # Начинаем с последней победы
    streak = 1
    prev_year = results[0].year
    prev_day = results[0].day

    # Проходим по остальным победам
    for i in range(1, len(results)):
        current_year = results[i].year
        current_day = results[i].day

        # Проверяем, что это последовательные дни
        # Если год тот же, проверяем что день на 1 меньше
        if current_year == prev_year:
            if prev_day - current_day == 1:
                streak += 1
                prev_day = current_day
            else:
                # Серия прервана
                break
        # Если год изменился, проверяем переход через границу года
        elif current_year == prev_year - 1:
            # Проверяем, что предыдущий день был 1 января (день 1)
            # А текущий — последний день предыдущего года
            if prev_day == 1:
                # Определяем последний день предыдущего года
                last_day = get_days_in_year(current_year)
                if current_day == last_day:
                    streak += 1
                    prev_year = current_year
                    prev_day = current_day
                else:
                    break
            else:
                break
        else:
            # Серия прервана (разрыв больше года)
            break

    logger.debug(f"Current win streak for user {user_id} in game {game_id}: {streak}")
    return streak


def check_first_blood(
    db_session,
    game_id: int,
    user_id: int,
    year: int
) -> Optional[UserAchievement]:
    """
    Проверить и выдать достижение "Первая кровь".

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        year: Год

    Returns:
        Выданное достижение или None
    """
    # Проверяем, есть ли уже это достижение
    if has_achievement(db_session, game_id, user_id, "first_blood", year):
        return None

    # Проверяем, что это первая победа пользователя в этом году
    stmt = select(GameResult).where(
        GameResult.game_id == game_id,
        GameResult.winner_id == user_id,
        GameResult.year == year
    )
    wins_count = len(db_session.exec(stmt).all())

    if wins_count == 1:
        # Это первая победа — выдаём достижение
        achievement = award_achievement(
            db_session,
            game_id,
            user_id,
            "first_blood",
            year
        )
        if achievement:
            logger.info(f"Awarded 'first_blood' achievement to user {user_id} in game {game_id}")
        return achievement

    return None


def check_streak_achievements(
    db_session,
    game_id: int,
    user_id: int,
    year: int
) -> List[UserAchievement]:
    """
    Проверить и выдать достижения за серии побед.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        year: Год

    Returns:
        Список выданных достижений
    """
    awarded = []

    # Получаем текущую серию побед
    streak = get_current_win_streak(db_session, game_id, user_id)

    # Проверяем достижения за серии (в порядке возрастания)
    streak_achievements = [
        ("streak_3", 3),
        ("streak_5", 5),
        ("streak_7", 7)
    ]

    for achievement_code, required_streak in streak_achievements:
        # Если серия достаточна и достижения ещё нет
        if streak >= required_streak:
            if not has_achievement(db_session, game_id, user_id, achievement_code, year):
                achievement = award_achievement(
                    db_session,
                    game_id,
                    user_id,
                    achievement_code,
                    year
                )
                if achievement:
                    awarded.append(achievement)
                    logger.info(
                        f"Awarded '{achievement_code}' achievement to user {user_id} "
                        f"in game {game_id} (streak: {streak})"
                    )

    return awarded


def check_and_award_achievements(
    db_session,
    game_id: int,
    user_id: int,
    year: int,
    day: int
) -> List[UserAchievement]:
    """
    Проверить и выдать все заслуженные достижения.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        year: Год
        day: День года

    Returns:
        Список выданных достижений
    """
    # Проверяем, включены ли достижения в конфигурации
    config = get_config_by_game_id(db_session, game_id)
    if not config.constants.achievements_enabled:
        logger.debug(f"Achievements disabled for game {game_id}")
        return []

    awarded = []

    # Проверяем "Первая кровь"
    first_blood = check_first_blood(db_session, game_id, user_id, year)
    if first_blood:
        awarded.append(first_blood)

    # Проверяем достижения за серии
    streak_achievements = check_streak_achievements(db_session, game_id, user_id, year)
    awarded.extend(streak_achievements)

    if awarded:
        logger.info(
            f"Awarded {len(awarded)} achievements to user {user_id} in game {game_id} "
            f"on {year}-{day}"
        )

    return awarded
