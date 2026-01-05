"""Service functions for working with pidor coins."""
import logging
from typing import List, Tuple, Optional

from sqlalchemy import func
from sqlmodel import select

from bot.app.models import PidorCoinTransaction, TGUser

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


def add_coins(db_session, game_id: int, user_id: int, amount: int, year: int, reason: str = "pidor_win") -> PidorCoinTransaction:
    """
    Начислить койны пользователю.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        amount: Количество койнов для начисления (положительное число)
        year: Год транзакции
        reason: Причина начисления (по умолчанию "pidor_win")

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
