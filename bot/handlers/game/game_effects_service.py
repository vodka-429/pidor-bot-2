"""Service functions for game effects (immunity, double chance)."""
import logging
from collections import Counter
from datetime import date, datetime
from typing import List, Set, Tuple
from unittest.mock import MagicMock

from sqlmodel import select

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
    """Разделить игроков на защищённых и незащищённых."""
    protected_players = []
    unprotected_players = []

    current_year = current_date.year
    current_day = current_date.timetuple().tm_yday

    for player in players:
        effect = get_or_create_player_effects(db_session, game_id, player.id)

        # Проверяем защиту: активна если год и день совпадают с текущими
        is_protected = (effect.immunity_year == current_year and effect.immunity_day == current_day)

        if is_protected:
            protected_players.append(player)
            logger.debug(f"Player {player.id} is protected on {current_year}-{current_day}")
        else:
            unprotected_players.append(player)

        db_session.add(effect)

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

    Игроки с активным двойным шансом добавляются в пул экспоненциально:
    1 покупка = 2^1 = 2 записи, 2 покупки = 2^2 = 4 записи, и т.д.
    """
    from bot.app.models import DoubleChancePurchase

    selection_pool = []
    players_with_double_chance = set()

    current_year = current_date.year
    current_day = current_date.timetuple().tm_yday

    # Получаем все активные покупки двойного шанса на сегодня
    stmt = select(DoubleChancePurchase).where(
        DoubleChancePurchase.game_id == game_id,
        DoubleChancePurchase.year == current_year,
        DoubleChancePurchase.day == current_day,
        DoubleChancePurchase.is_used == False
    )
    active_purchases = db_session.exec(stmt).all()

    # Подсчитываем количество покупок для каждого игрока
    purchase_counts = Counter(p.target_id for p in active_purchases)

    for player in players:
        purchase_count = purchase_counts.get(player.id, 0)

        if purchase_count > 0:
            # Экспоненциальная логика: 2^n записей
            entries_count = 2 ** purchase_count
            for _ in range(entries_count):
                selection_pool.append(player)
            players_with_double_chance.add(player.id)
            logger.debug(f"Player {player.id} ({player.full_username()}) has {purchase_count} double chance purchase(s), added {entries_count} times")
        else:
            # Добавляем игрока один раз
            selection_pool.append(player)

    logger.info(f"Built selection pool: {len(selection_pool)} entries, {len(players_with_double_chance)} players with double chance")
    return selection_pool, players_with_double_chance


def check_winner_immunity(
    db_session,
    game_id: int,
    winner: TGUser,
    current_date: date
) -> bool:
    """Проверить, защищён ли победитель."""
    winner_effect = get_or_create_player_effects(db_session, game_id, winner.id)

    current_year = current_date.year
    current_day = current_date.timetuple().tm_yday

    is_protected = (winner_effect.immunity_year == current_year and winner_effect.immunity_day == current_day)

    if is_protected:
        logger.info(f"Winner {winner.id} ({winner.full_username()}) is protected on {current_year}-{current_day}")

    db_session.add(winner_effect)
    return is_protected


def reset_double_chance(
    db_session,
    game_id: int,
    user_id: int,
    current_date: date
):
    """
    Сбросить двойной шанс после победы.

    Помечает все активные покупки двойного шанса для этого игрока как использованные.
    """
    from bot.app.models import DoubleChancePurchase

    current_year = current_date.year
    current_day = current_date.timetuple().tm_yday

    # Находим все активные покупки двойного шанса для этого игрока на сегодня
    stmt = select(DoubleChancePurchase).where(
        DoubleChancePurchase.game_id == game_id,
        DoubleChancePurchase.target_id == user_id,
        DoubleChancePurchase.year == current_year,
        DoubleChancePurchase.day == current_day,
        DoubleChancePurchase.is_used == False
    )
    purchases = db_session.exec(stmt).all()

    for purchase in purchases:
        logger.info(f"Marking double chance purchase {purchase.id} as used for user {user_id}")
        purchase.is_used = True
        db_session.add(purchase)


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
