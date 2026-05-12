"""Service functions for game effects (immunity, double chance)."""
import calendar
import logging
from collections import Counter
from datetime import date, datetime
from typing import List, Optional, Set, Tuple
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


def is_player_birthday(player: TGUser, current_date: date) -> bool:
    """Проверяет, что сегодня у игрока день рождения.

    29 февраля в невисокосный год считаем за 28.02 — иначе человек никогда
    не получит бонус.
    """
    month = player.birth_month
    day = player.birth_day
    if month is None or day is None:
        return False

    if month == current_date.month and day == current_date.day:
        return True

    # 29.02 в невисокосный год → отмечаем 28.02
    if (month == 2 and day == 29
            and current_date.month == 2 and current_date.day == 28
            and not calendar.isleap(current_date.year)):
        return True

    return False


def build_selection_pool(
    db_session,
    game_id: int,
    players: List[TGUser],
    current_date: date,
    birthday_multiplier: int = 1,
) -> Tuple[List[TGUser], Set[int], Set[int]]:
    """
    Создать пул выбора с учётом двойного шанса и бонуса именинника.

    Игроки с активным двойным шансом добавляются в пул экспоненциально:
    1 покупка = 2^1 = 2 записи, 2 покупки = 2^2 = 4 записи, и т.д.

    Если у игрока сегодня день рождения, его количество записей домножается
    на `birthday_multiplier`. При `birthday_multiplier == 1` фича отключена.
    """
    from bot.app.models import DoubleChancePurchase

    selection_pool = []
    players_with_double_chance = set()
    players_with_birthday = set()

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
        has_birthday = birthday_multiplier > 1 and is_player_birthday(player, current_date)

        entries_count = (2 ** purchase_count) if purchase_count > 0 else 1
        if has_birthday:
            entries_count *= birthday_multiplier
            players_with_birthday.add(player.id)

        for _ in range(entries_count):
            selection_pool.append(player)

        if purchase_count > 0:
            players_with_double_chance.add(player.id)

        if entries_count > 1:
            logger.debug(
                f"Player {player.id} ({player.full_username()}) entries={entries_count} "
                f"(double_chance={purchase_count}, birthday={has_birthday})"
            )

    logger.info(
        f"Built selection pool: {len(selection_pool)} entries, "
        f"{len(players_with_double_chance)} with double chance, "
        f"{len(players_with_birthday)} with birthday"
    )
    return selection_pool, players_with_double_chance, players_with_birthday


def check_winner_immunity(
    db_session,
    game_id: int,
    winner: TGUser,
    current_date: date
) -> Optional[int]:
    """Проверить, защищён ли победитель.

    Returns:
        immunity_buyer_id если защищён (может совпадать с winner.id при самозащите),
        None если не защищён.
    """
    winner_effect = get_or_create_player_effects(db_session, game_id, winner.id)

    current_year = current_date.year
    current_day = current_date.timetuple().tm_yday

    is_protected = (winner_effect.immunity_year == current_year and winner_effect.immunity_day == current_day)

    if is_protected:
        logger.info(f"Winner {winner.id} ({winner.full_username()}) is protected on {current_year}-{current_day}")
        db_session.add(winner_effect)
        # Если buyer_id не заполнен (старые записи до фичи), считаем самозащитой
        return winner_effect.immunity_buyer_id if winner_effect.immunity_buyer_id is not None else winner.id

    db_session.add(winner_effect)
    return None


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
