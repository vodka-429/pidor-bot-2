"""Service functions for achievements system."""
import logging
from typing import List, Optional, Tuple
from datetime import datetime, date
from calendar import monthrange

from sqlmodel import select, func, text

from bot.app.models import UserAchievement, GameResult, TGUser, PidorCoinTransaction
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
        ("streak_2", 2),
        ("streak_3", 3),
        ("streak_5", 5)
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



def get_previous_month(year: int, month: int) -> Tuple[int, int]:
    """
    Получить предыдущий месяц с учётом перехода года.

    Args:
        year: Текущий год
        month: Текущий месяц (1-12)

    Returns:
        Кортеж (год, месяц) для предыдущего месяца
    """
    if month == 1:
        return year - 1, 12
    return year, month - 1


def is_first_game_of_month(
    db_session,
    game_id: int,
    year: int,
    month: int,
    day: int
) -> bool:
    """
    Проверить, первый ли это розыгрыш в месяце.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры
        year: Год
        month: Месяц (1-12)
        day: День месяца (1-31)

    Returns:
        True если это первый розыгрыш месяца, False иначе
    """
    # Вычисляем день года для первого дня месяца
    first_day_of_month = date(year, month, 1).timetuple().tm_yday
    # Вычисляем день года для текущего дня
    current_day_of_year = date(year, month, day).timetuple().tm_yday

    # Ищем розыгрыши в текущем месяце до текущего дня
    stmt = select(GameResult).where(
        GameResult.game_id == game_id,
        GameResult.year == year,
        GameResult.day >= first_day_of_month,
        GameResult.day < current_day_of_year  # Строго меньше текущего дня
    )

    previous_games = db_session.exec(stmt).all()
    is_first = len(previous_games) == 0

    logger.debug(
        f"Checking if first game of month for game {game_id}, {year}-{month:02d}-{day:02d}: "
        f"{is_first} (found {len(previous_games)} previous games)"
    )

    return is_first


def get_monthly_winners(
    db_session,
    game_id: int,
    year: int,
    month: int
) -> List[Tuple[int, int]]:
    """
    Получить лидеров по победам за месяц.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры
        year: Год
        month: Месяц (1-12)

    Returns:
        Список кортежей (user_id, wins_count), отсортированный по убыванию побед
    """
    # Вычисляем диапазон дней для месяца
    first_day = date(year, month, 1).timetuple().tm_yday
    last_day_of_month = monthrange(year, month)[1]
    last_day = date(year, month, last_day_of_month).timetuple().tm_yday

    stmt = select(GameResult.winner_id, func.count(GameResult.id).label('wins')) \
        .where(
            GameResult.game_id == game_id,
            GameResult.year == year,
            GameResult.day >= first_day,
            GameResult.day <= last_day
        ) \
        .group_by(GameResult.winner_id) \
        .order_by(text('wins DESC'))

    results = db_session.exec(stmt).all()
    winners = [(r[0], r[1]) for r in results]

    logger.debug(
        f"Monthly winners for game {game_id}, {year}-{month:02d}: "
        f"{len(winners)} players, top: {winners[:3] if winners else 'none'}"
    )

    return winners


def get_monthly_initiators(
    db_session,
    game_id: int,
    year: int,
    month: int
) -> List[Tuple[int, int]]:
    """
    Получить лидеров по запускам /pidor за месяц.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры
        year: Год
        month: Месяц (1-12)

    Returns:
        Список кортежей (user_id, commands_count), отсортированный по убыванию
    """
    # Вычисляем временной диапазон для месяца
    first_day_date = date(year, month, 1)
    last_day_of_month = monthrange(year, month)[1]
    last_day_date = date(year, month, last_day_of_month)

    # Создаём datetime объекты для начала и конца месяца
    start_datetime = datetime(year, month, 1, 0, 0, 0)
    end_datetime = datetime(year, month, last_day_of_month, 23, 59, 59)

    # Считаем транзакции с reason="command_execution"
    stmt = select(PidorCoinTransaction.user_id, func.count(PidorCoinTransaction.id).label('commands')) \
        .where(
            PidorCoinTransaction.game_id == game_id,
            PidorCoinTransaction.year == year,
            PidorCoinTransaction.reason == "command_execution",
            PidorCoinTransaction.created_at >= start_datetime,
            PidorCoinTransaction.created_at <= end_datetime
        ) \
        .group_by(PidorCoinTransaction.user_id) \
        .order_by(text('commands DESC'))

    results = db_session.exec(stmt).all()
    initiators = [(r[0], r[1]) for r in results]

    logger.debug(
        f"Monthly initiators for game {game_id}, {year}-{month:02d}: "
        f"{len(initiators)} players, top: {initiators[:3] if initiators else 'none'}"
    )

    return initiators


def check_monthly_achievements(
    db_session,
    game_id: int,
    year: int,
    month: int
) -> List[UserAchievement]:
    """
    Проверить и выдать ежемесячные достижения.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры
        year: Год
        month: Месяц (1-12)

    Returns:
        Список выданных достижений
    """
    awarded = []

    # Проверяем "Король месяца"
    winners = get_monthly_winners(db_session, game_id, year, month)
    if winners:
        max_wins = winners[0][1]
        # Все с максимальным количеством побед получают достижение
        for user_id, wins in winners:
            if wins == max_wins:
                achievement = award_achievement(
                    db_session, game_id, user_id,
                    "monthly_king", year, period=month
                )
                if achievement:
                    awarded.append(achievement)
                    logger.info(
                        f"Awarded 'monthly_king' to user {user_id} in game {game_id} "
                        f"for {year}-{month:02d} ({wins} wins)"
                    )
            else:
                break  # Остальные имеют меньше побед

    # Проверяем "Инициатор месяца"
    initiators = get_monthly_initiators(db_session, game_id, year, month)
    if initiators:
        max_commands = initiators[0][1]
        # Все с максимальным количеством запусков получают достижение
        for user_id, commands in initiators:
            if commands == max_commands:
                achievement = award_achievement(
                    db_session, game_id, user_id,
                    "monthly_initiator", year, period=month
                )
                if achievement:
                    awarded.append(achievement)
                    logger.info(
                        f"Awarded 'monthly_initiator' to user {user_id} in game {game_id} "
                        f"for {year}-{month:02d} ({commands} commands)"
                    )
            else:
                break

    logger.info(
        f"Awarded {len(awarded)} monthly achievements for game {game_id}, {year}-{month:02d}"
    )

    return awarded
