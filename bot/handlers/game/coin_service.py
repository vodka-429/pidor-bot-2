"""Service functions for working with pidor coins."""
import logging
from typing import Dict, Iterable, List, Tuple, Optional

from sqlalchemy import func
from sqlmodel import select

from bot.app.models import DEPOSIT_STATUS_OPEN, CoinDeposit, PidorCoinTransaction, TGUser

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


def get_balances(db_session, game_id: int, user_ids: Iterable[int]) -> Dict[int, int]:
    """Балансы за всё время для набора игроков одним запросом; у игроков без транзакций — 0."""
    ids = [user_id for user_id in user_ids if user_id is not None]
    balances = {user_id: 0 for user_id in ids}
    if not ids:
        return balances
    rows = db_session.exec(
        select(PidorCoinTransaction.user_id, func.sum(PidorCoinTransaction.amount))
        .where(
            PidorCoinTransaction.game_id == game_id,
            PidorCoinTransaction.user_id.in_(ids),
        )
        .group_by(PidorCoinTransaction.user_id)
    ).all()
    for user_id, total in rows:
        balances[user_id] = total or 0
    return balances


def get_open_deposit_amounts(db_session, game_id: int) -> Dict[int, int]:
    """Тела открытых вкладов чата: {user_id: amount}."""
    rows = db_session.exec(
        select(CoinDeposit.user_id, CoinDeposit.amount).where(
            CoinDeposit.game_id == game_id,
            CoinDeposit.status == DEPOSIT_STATUS_OPEN,
        )
    ).all()
    amounts: Dict[int, int] = {}
    for user_id, amount in rows:
        amounts[user_id] = amounts.get(user_id, 0) + amount
    return amounts


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


def get_leaderboard_by_year(db_session, game_id: int, year: int, limit: Optional[int] = 50) -> List[Tuple[TGUser, int]]:
    """
    Получить топ по койнам за конкретный год.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        year: Год для статистики
        limit: Количество записей в топе (по умолчанию 10), None — без ограничения

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


def get_leaderboard_by_year_with_deposits(
    db_session, game_id: int, year: int, limit: int = 50
) -> List[Tuple[TGUser, int]]:
    """
    Топ за год с открытыми вкладами: тело вклада прибавляется к годовой сумме игрока,
    чтобы койны нельзя было спрятать на вкладе. Без вкладов — то же, что get_leaderboard_by_year.
    """
    deposits = get_open_deposit_amounts(db_session, game_id)
    if not deposits:
        return get_leaderboard_by_year(db_session, game_id, year, limit=limit)

    totals: Dict[int, List] = {
        user.id: [user, coins]
        for user, coins in get_leaderboard_by_year(db_session, game_id, year, limit=None)
    }
    for user_id, amount in deposits.items():
        if user_id in totals:
            totals[user_id][1] += amount
            continue
        user = db_session.get(TGUser, user_id)
        if user is not None:
            totals[user_id] = [user, amount]

    board = sorted(((user, coins) for user, coins in totals.values()), key=lambda item: item[1], reverse=True)
    return board[:limit]


def compute_redistribution_swap(
    db_session,
    game_id: int,
    cur_year: int,
    winner: TGUser,
    active_players: List[TGUser],
    include_deposits: bool = False,
) -> Optional[Tuple[TGUser, int, int, int]]:
    """
    Рассчитать своп монет для self-pidor из bottom-N%.

    Вызывать ПОСЛЕ add_coins(self_pidor_coins, auto_commit=False) —
    autoflush включит их в leaderboard-запрос автоматически.

    include_deposits: тела открытых вкладов считаются частью годового баланса. Сам своп
    двигает только кошельки, поэтому delta не больше кошелька богатого игрока.

    Returns:
        (rich_user, winner_final_coins, rich_coins, delta) или None.
        После свопа: winner → rich_coins, rich_user → winner_final_coins.
    """
    n = len(active_players)
    if n <= 10:
        return None
    swap_size = max(1, round(n * 0.1))

    active_ids = {p.id for p in active_players}
    deposits = get_open_deposit_amounts(db_session, game_id) if include_deposits else {}
    raw = get_leaderboard_by_year(db_session, game_id, cur_year, limit=n + 20)

    board = [(u, c + deposits.get(u.id, 0)) for u, c in raw if u.id in active_ids]

    board_ids = {u.id for u, _ in board}
    for p in active_players:
        if p.id not in board_ids:
            board.append((p, deposits.get(p.id, 0)))

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
    if deposits.get(rich_user.id, 0) > 0:
        delta = min(delta, max(get_balance(db_session, game_id, rich_user.id), 0))
    if delta <= 0:
        return None

    logger.debug(
        f"Redistribution swap: winner {winner.id} ({winner_final} coins) "
        f"↔ rich {rich_user.id} ({rich_coins} coins), delta={delta}"
    )
    return (rich_user, winner_final, rich_coins, delta)
