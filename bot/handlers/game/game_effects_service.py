"""Service functions for game effects (immunity, double chance)."""
import logging
from datetime import date, datetime
from typing import List, Set, Tuple
from unittest.mock import MagicMock

from bot.app.models import TGUser, GamePlayerEffect
from bot.handlers.game.shop_service import get_or_create_player_effects
from bot.utils import to_date

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


def filter_protected_players(
    db_session,
    game_id: int,
    players: List[TGUser],
    current_date: date
) -> Tuple[List[TGUser], List[TGUser]]:
    """
    Разделить игроков на защищённых и незащищённых.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        players: Список всех игроков
        current_date: Текущая дата

    Returns:
        Кортеж (незащищённые игроки, защищённые игроки)
    """
    protected_players = []
    unprotected_players = []

    for player in players:
        effect = get_or_create_player_effects(db_session, game_id, player.id)
        immunity_date = to_date(effect.immunity_until)
        if immunity_date and immunity_date >= current_date:
            protected_players.append(player)
            logger.debug(f"Player {player.id} ({player.full_username()}) is protected until {effect.immunity_until}")
        else:
            unprotected_players.append(player)
        db_session.add(effect)  # Добавляем эффект в сессию

    logger.info(f"Filtered players: {len(unprotected_players)} unprotected, {len(protected_players)} protected")
    return unprotected_players, protected_players


def build_selection_pool(
    db_session,
    game_id: int,
    players: List[TGUser],
    current_date: date
) -> Tuple[List[TGUser], Set[int]]:
    """
    Создать пул выбора с учётом двойного шанса.

    Игроки с активным двойным шансом добавляются в пул дважды,
    что удваивает их шанс быть выбранными.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        players: Список игроков для пула
        current_date: Текущая дата

    Returns:
        Кортеж (пул выбора, set ID игроков с двойным шансом)
    """
    selection_pool = []
    players_with_double_chance = set()

    for player in players:
        effect = get_or_create_player_effects(db_session, game_id, player.id)

        # Проверяем активность двойного шанса
        double_chance_date = to_date(effect.double_chance_until)
        if double_chance_date and double_chance_date >= current_date:
            # Добавляем игрока дважды (двойной шанс)
            selection_pool.append(player)
            selection_pool.append(player)
            players_with_double_chance.add(player.id)
            logger.debug(f"Player {player.id} ({player.full_username()}) has double chance until {effect.double_chance_until}")
        else:
            # Добавляем игрока один раз
            selection_pool.append(player)
        db_session.add(effect)  # Добавляем эффект в сессию

    logger.info(f"Built selection pool: {len(selection_pool)} entries, {len(players_with_double_chance)} players with double chance")
    return selection_pool, players_with_double_chance


def check_winner_immunity(
    db_session,
    game_id: int,
    winner: TGUser,
    current_date: date
) -> bool:
    """
    Проверить, защищён ли победитель.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        winner: Победитель для проверки
        current_date: Текущая дата

    Returns:
        True если победитель защищён, False иначе
    """
    winner_effect = get_or_create_player_effects(db_session, game_id, winner.id)

    immunity_date = to_date(winner_effect.immunity_until)
    if immunity_date and immunity_date >= current_date:
        logger.info(f"Winner {winner.id} ({winner.full_username()}) is protected until {winner_effect.immunity_until}")
        db_session.add(winner_effect)  # Добавляем эффект в сессию
        return True

    db_session.add(winner_effect)  # Добавляем эффект в сессию
    return False


def reset_double_chance(
    db_session,
    game_id: int,
    user_id: int,
    current_date: date
):
    """
    Сбросить двойной шанс после победы.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        current_date: Текущая дата
    """
    effect = get_or_create_player_effects(db_session, game_id, user_id)

    double_chance_date = to_date(effect.double_chance_until)
    if double_chance_date and double_chance_date >= current_date:
        logger.info(f"Resetting double chance for user {user_id}")
        effect.double_chance_until = None
        db_session.add(effect)  # Явно добавляем изменённый объект в сессию
        # Коммит будет выполнен позже вместе с остальными изменениями


def is_immunity_enabled(current_datetime: datetime) -> bool:
    """
    Проверить, включена ли защита (не последний день года).

    В последний день года (31 декабря) защита не работает.

    Args:
        current_datetime: Текущая дата и время

    Returns:
        True если защита включена, False если последний день года
    """
    is_last_day = current_datetime.month == 12 and current_datetime.day >= 31
    return not is_last_day
