"""Service functions for working with pidor coins."""
import logging
from typing import List, Tuple, Optional

from sqlalchemy import func
from sqlmodel import select

from bot.app.models import PidorCoinTransaction, TGUser

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


def add_coins(db_session, game_id: int, user_id: int, amount: int, year: int, reason: str = "pidor_win", auto_commit: bool = True) -> PidorCoinTransaction:
    """
    Начислить койны пользователю.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        amount: Количество койнов для начисления (положительное число)
        year: Год транзакции
        reason: Причина начисления (по умолчанию "pidor_win")
        auto_commit: Автоматически коммитить транзакцию (по умолчанию True)

    Returns:
        Созданная транзакция PidorCoinTransaction
    """
    if amount <= 0:
        raise ValueError("Amount must be positive")

    # Создаем новую транзакцию
    transaction = PidorCoinTransaction(
        game_id=game_id,
        user_id=user_id,
        amount=amount,
        year=year,
        reason=reason
    )

    db_session.add(transaction)

    if auto_commit:
        db_session.commit()
        db_session.refresh(transaction)

    logger.info(f"Added {amount} coins to user {user_id} in game {game_id} for year {year}, reason: {reason}")

    return transaction


def get_balance(db_session, game_id: int, user_id: int) -> int:
    """
    Получить общий баланс койнов пользователя в игре.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя

    Returns:
        Сумма всех койнов пользователя в игре
    """
    stmt = select(func.sum(PidorCoinTransaction.amount)) \
        .where(
            PidorCoinTransaction.game_id == game_id,
            PidorCoinTransaction.user_id == user_id
        )

    result = db_session.exec(stmt).first()
    logger.debug(f"get_balance result: {result}, type: {type(result)}")
    # func.sum() возвращает скалярное значение (int), а не кортеж
    return result if result is not None else 0


def get_leaderboard(db_session, game_id: int, limit: int = 50) -> List[Tuple[TGUser, int]]:
    """
    Получить топ по койнам за всё время.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        limit: Количество записей в топе (по умолчанию 10)

    Returns:
        Список кортежей (TGUser, сумма койнов), отсортированный по убыванию
    """
    stmt = select(
        TGUser,
        func.sum(PidorCoinTransaction.amount).label('total_coins')
    ) \
        .join(PidorCoinTransaction, PidorCoinTransaction.user_id == TGUser.id) \
        .where(PidorCoinTransaction.game_id == game_id) \
        .group_by(TGUser) \
        .order_by(func.sum(PidorCoinTransaction.amount).desc()) \
        .limit(limit)

    return db_session.exec(stmt).all()


def get_leaderboard_by_year(db_session, game_id: int, year: int, limit: int = 50) -> List[Tuple[TGUser, int]]:
    """
    Получить топ по койнам за конкретный год.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        year: Год для статистики
        limit: Количество записей в топе (по умолчанию 10)

    Returns:
        Список кортежей (TGUser, сумма койнов за год), отсортированный по убыванию
    """
    stmt = select(
        TGUser,
        func.sum(PidorCoinTransaction.amount).label('total_coins')
    ) \
        .join(PidorCoinTransaction, PidorCoinTransaction.user_id == TGUser.id) \
        .where(
            PidorCoinTransaction.game_id == game_id,
            PidorCoinTransaction.year == year
        ) \
        .group_by(TGUser) \
        .order_by(func.sum(PidorCoinTransaction.amount).desc()) \
        .limit(limit)

    return db_session.exec(stmt).all()


def compute_redistribution_swap(
    db_session,
    game_id: int,
    cur_year: int,
    winner: TGUser,
    active_players: List[TGUser],
) -> Optional[Tuple[TGUser, int, int, int]]:
    """
    Рассчитать своп монет для self-pidor из bottom-N%.

    Вызывать ПОСЛЕ add_coins(self_pidor_coins, auto_commit=False) —
    autoflush включит их в leaderboard-запрос автоматически.

    Returns:
        (rich_user, winner_final_coins, rich_coins, delta) или None.
        После свопа: winner → rich_coins, rich_user → winner_final_coins.
    """
    n = len(active_players)
    if n <= 10:
        return None
    swap_size = max(1, round(n * 0.1))

    active_ids = {p.id for p in active_players}
    raw = get_leaderboard_by_year(db_session, game_id, cur_year, limit=n + 20)

    board = [(u, c) for u, c in raw if u.id in active_ids]

    board_ids = {u.id for u, _ in board}
    for p in active_players:
        if p.id not in board_ids:
            board.append((p, 0))

    board.sort(key=lambda x: x[1], reverse=True)

    # Bottom-N по возрастанию (беднейший первый)
    bottom_n = sorted(board[-swap_size:], key=lambda x: x[1])
    if not any(u.id == winner.id for u, _ in bottom_n):
        return None

    winner_final = next(c for u, c in board if u.id == winner.id)
    winner_idx = next(i for i, (u, _) in enumerate(bottom_n) if u.id == winner.id)
    rich_user, rich_coins = board[winner_idx]

    if rich_user.id == winner.id:
        return None

    delta = rich_coins - winner_final
    if delta <= 0:
        return None

    logger.debug(
        f"Redistribution swap: winner {winner.id} ({winner_final} coins) "
        f"↔ rich {rich_user.id} ({rich_coins} coins), delta={delta}"
    )
    return (rich_user, winner_final, rich_coins, delta)
