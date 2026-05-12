"""Service for selecting winners with game effects (immunity, double chance)."""
import logging
import random
from dataclasses import dataclass
from datetime import date
from typing import List, Set, Optional

from bot.app.models import TGUser
from bot.handlers.game.game_effects_service import (
    filter_protected_players,
    build_selection_pool,
    check_winner_immunity,
    is_immunity_enabled
)

logger = logging.getLogger(__name__)


@dataclass
class SelectionResult:
    """Result of winner selection with metadata."""
    winner: TGUser
    had_immunity: bool  # Был ли у победителя иммунитет (и произошёл перевыбор)
    had_double_chance: bool  # Был ли у победителя двойной шанс
    all_protected: bool  # Были ли все игроки защищены
    protected_player: Optional[TGUser] = None  # Игрок, который был защищён (если была защита)
    immunity_buyer_id: Optional[int] = None  # Кто купил защиту сработавшему игроку
    had_birthday_bonus: bool = False  # Был ли у победителя бонус именинника
    birthday_players: List[TGUser] = None  # Все именинники среди игроков (для анонса)

    def __post_init__(self):
        if self.birthday_players is None:
            self.birthday_players = []


def build_selection_context(
    db_session,
    game_id: int,
    players: List[TGUser],
    current_date: date,
    immunity_enabled: bool = True,
    birthday_multiplier: int = 1,
) -> tuple[List[TGUser], List[TGUser], List[TGUser], Set[int], Set[int]]:
    """
    Подготовить контекст для выбора победителя.

    Args:
        db_session: Сессия БД
        game_id: ID игры
        players: Список всех игроков
        current_date: Текущая дата
        immunity_enabled: Включена ли защита (по умолчанию True)
        birthday_multiplier: Множитель для именинника (1 = фича отключена)

    Returns:
        Кортеж из:
        - selection_pool: Пул для выбора (с учётом двойного шанса и ДР)
        - unprotected_players: Незащищённые игроки
        - protected_players: Защищённые игроки
        - players_with_double_chance: Множество ID игроков с двойным шансом
        - players_with_birthday: Множество ID именинников
    """
    # Если защита включена, фильтруем защищённых игроков
    if immunity_enabled:
        unprotected_players, protected_players = filter_protected_players(
            db_session, game_id, players, current_date
        )
    else:
        # Если защита выключена, все игроки незащищённые
        unprotected_players = players
        protected_players = []

    # Создаём пул выбора с учётом двойного шанса и бонуса именинника
    selection_pool, players_with_double_chance, players_with_birthday = build_selection_pool(
        db_session, game_id, players, current_date, birthday_multiplier=birthday_multiplier
    )

    logger.debug(
        f"Selection context: {len(selection_pool)} in pool, "
        f"{len(unprotected_players)} unprotected, "
        f"{len(protected_players)} protected, "
        f"{len(players_with_double_chance)} with double chance, "
        f"{len(players_with_birthday)} with birthday"
    )

    return (
        selection_pool,
        unprotected_players,
        protected_players,
        players_with_double_chance,
        players_with_birthday,
    )


def select_winner_with_effects(
    db_session,
    game_id: int,
    players: List[TGUser],
    current_date: date,
    immunity_enabled: bool = True,
    birthday_multiplier: int = 1,
) -> Optional[SelectionResult]:
    """
    Выбрать победителя с учётом защиты, двойного шанса и бонуса именинника.

    Args:
        db_session: Сессия БД
        game_id: ID игры
        players: Список всех игроков
        current_date: Текущая дата
        immunity_enabled: Включена ли защита (по умолчанию True)
        birthday_multiplier: Множитель шанса для именинника (1 = фича отключена)

    Returns:
        SelectionResult с информацией о выборе или None если все защищены
    """
    # Подготавливаем контекст для выбора
    (
        selection_pool,
        unprotected_players,
        protected_players,
        players_with_double_chance,
        players_with_birthday,
    ) = build_selection_context(
        db_session, game_id, players, current_date, immunity_enabled, birthday_multiplier
    )

    birthday_players = [p for p in players if p.id in players_with_birthday]

    # Если все игроки защищены - возвращаем None
    if immunity_enabled and len(unprotected_players) == 0:
        logger.warning(f"All players are protected in game {game_id}")
        return SelectionResult(
            winner=None,
            had_immunity=False,
            had_double_chance=False,
            all_protected=True,
            birthday_players=birthday_players,
        )

    # Выбираем победителя из пула
    winner = random.choice(selection_pool)
    logger.info(f"Winner selected: {winner.full_username()}")

    # Запоминаем эффекты, сработавшие на победителя
    winner_had_double_chance = winner.id in players_with_double_chance
    winner_had_birthday = winner.id in players_with_birthday

    # Проверяем защиту победителя только если она включена
    had_immunity = False
    protected_player = None
    immunity_buyer_id = None
    if immunity_enabled:
        buyer_id = check_winner_immunity(db_session, game_id, winner, current_date)
        if buyer_id is not None:
            logger.info(f"Winner {winner.id} ({winner.full_username()}) is protected, reselecting")
            had_immunity = True
            protected_player = winner  # Сохраняем защищённого игрока
            immunity_buyer_id = buyer_id

            # Перевыбираем из незащищенных игроков
            winner = random.choice(unprotected_players)
            logger.info(f"Reselected winner after immunity: {winner.full_username()}")

            # Обновляем информацию об эффектах для нового победителя
            winner_had_double_chance = winner.id in players_with_double_chance
            winner_had_birthday = winner.id in players_with_birthday

    return SelectionResult(
        winner=winner,
        had_immunity=had_immunity,
        had_double_chance=winner_had_double_chance,
        all_protected=False,
        protected_player=protected_player,
        immunity_buyer_id=immunity_buyer_id,
        had_birthday_bonus=winner_had_birthday,
        birthday_players=birthday_players,
    )
