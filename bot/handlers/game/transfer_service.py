"""Service functions for coin transfer functionality."""
import logging
from datetime import datetime
from typing import Tuple, Optional

from sqlmodel import select

from bot.app.models import CoinTransfer, ChatBank
from bot.handlers.game.coin_service import add_coins
from bot.handlers.game.shop_service import spend_coins

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Константы передачи койнов
TRANSFER_COMMISSION_PERCENT = 10
TRANSFER_MIN_COMMISSION = 1
TRANSFER_MIN_AMOUNT = 2


def calculate_commission(amount: int) -> int:
    """
    Рассчитать комиссию за перевод.

    Args:
        amount: Сумма перевода

    Returns:
        Размер комиссии (минимум TRANSFER_MIN_COMMISSION)
    """
    commission = amount * TRANSFER_COMMISSION_PERCENT // 100
    return max(commission, TRANSFER_MIN_COMMISSION)


def has_transferred_today(db_session, game_id: int, sender_id: int, year: int, day: int) -> bool:
    """
    Проверить, совершал ли игрок перевод сегодня (по year+day).

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        sender_id: ID отправителя
        year: Год
        day: День года (1-366)

    Returns:
        True если перевод уже был сегодня, False иначе
    """
    stmt = select(CoinTransfer).where(
        CoinTransfer.game_id == game_id,
        CoinTransfer.sender_id == sender_id,
        CoinTransfer.year == year,
        CoinTransfer.day == day
    )
    existing_transfer = db_session.exec(stmt).first()

    has_transfer = existing_transfer is not None
    logger.debug(f"User {sender_id} has transferred today ({year}-{day}): {has_transfer}")
    return has_transfer


def can_transfer(db_session, game_id: int, sender_id: int, year: int, day: int) -> Tuple[bool, str]:
    """
    Проверить, может ли игрок совершить перевод.
    Кулдаун проверяется по year+day (как остальные эффекты).

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        sender_id: ID отправителя
        year: Год
        day: День года (1-366)

    Returns:
        Кортеж (can_transfer, error_message)
        error_message может быть: "ok" или "already_transferred_today"
    """
    if has_transferred_today(db_session, game_id, sender_id, year, day):
        return False, "already_transferred_today"

    return True, "ok"


def get_or_create_chat_bank(db_session, game_id: int) -> ChatBank:
    """
    Получить или создать банк чата.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)

    Returns:
        Объект ChatBank
    """
    stmt = select(ChatBank).where(ChatBank.game_id == game_id)
    bank = db_session.exec(stmt).first()

    if bank is None:
        bank = ChatBank(game_id=game_id, balance=0)
        db_session.add(bank)
        db_session.commit()
        db_session.refresh(bank)
        logger.info(f"Created new ChatBank for game {game_id}")

    return bank


def execute_transfer(
    db_session,
    game_id: int,
    sender_id: int,
    receiver_id: int,
    amount: int,
    year: int,
    day: int
) -> Tuple[int, int, int]:
    """
    Выполнить перевод койнов.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        sender_id: ID отправителя
        receiver_id: ID получателя
        amount: Сумма перевода (до комиссии)
        year: Год
        day: День года (1-366)

    Returns:
        Кортеж (amount_sent, amount_received, commission)

    Raises:
        ValueError: Если сумма меньше минимальной или отправитель = получатель
    """
    if amount < TRANSFER_MIN_AMOUNT:
        raise ValueError(f"Amount must be at least {TRANSFER_MIN_AMOUNT}")

    if sender_id == receiver_id:
        raise ValueError("Cannot transfer to yourself")

    # Рассчитываем комиссию
    commission = calculate_commission(amount)
    amount_received = amount - commission

    logger.info(
        f"Executing transfer: sender={sender_id}, receiver={receiver_id}, "
        f"amount={amount}, commission={commission}, received={amount_received}"
    )

    # Списываем с отправителя
    spend_coins(
        db_session, game_id, sender_id, amount, year,
        f"transfer_to_{receiver_id}", auto_commit=False
    )

    # Начисляем получателю
    add_coins(
        db_session, game_id, receiver_id, amount_received, year,
        f"transfer_from_{sender_id}", auto_commit=False
    )

    # Добавляем комиссию в банк
    bank = get_or_create_chat_bank(db_session, game_id)
    bank.balance += commission
    bank.updated_at = datetime.utcnow()
    db_session.add(bank)

    # Создаём запись о переводе (с year+day для кулдауна)
    transfer = CoinTransfer(
        game_id=game_id,
        sender_id=sender_id,
        receiver_id=receiver_id,
        amount=amount,
        commission=commission,
        year=year,
        day=day
    )
    db_session.add(transfer)

    db_session.commit()

    logger.info(
        f"Transfer completed: {amount} coins from {sender_id} to {receiver_id}, "
        f"commission {commission} to bank, game {game_id}, {year}-{day}"
    )

    return amount, amount_received, commission
