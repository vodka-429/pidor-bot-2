"""Service functions for toast functionality."""
import logging
from datetime import datetime
from typing import Tuple

from bot.app.models import Toast, ChatBank
from bot.handlers.game.coin_service import add_coins
from bot.handlers.game.shop_service import spend_coins
from bot.handlers.game.cbr_service import calculate_commission_amount
from bot.handlers.game.config import get_config_by_game_id
from sqlmodel import select

logger = logging.getLogger(__name__)


def calculate_toast_commission(amount: int) -> int:
    """
    Рассчитать комиссию за тост по ключевой ставке ЦБ РФ.

    Args:
        amount: Стоимость тоста

    Returns:
        Размер комиссии (минимум 1 койн)
    """
    return calculate_commission_amount(amount)


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


def execute_toast(
    db_session,
    game_id: int,
    sender_id: int,
    receiver_id: int,
    year: int,
) -> Tuple[int, int, int]:
    """
    Выполнить тост — отправить fixed-price перевод с комиссией.

    Ограничений на количество тостов в день нет. Тост за себя разрешён.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        sender_id: ID отправителя (внутренний ID БД)
        receiver_id: ID получателя (внутренний ID БД)
        year: Год тоста (для статистики)

    Returns:
        Кортеж (amount_sent, amount_received, commission)

    Raises:
        ValueError: Если тосты отключены или недостаточно средств
    """
    config = get_config_by_game_id(db_session, game_id)

    if not config.constants.toast_enabled:
        raise ValueError("Toast is disabled for this chat")

    price = config.constants.toast_price
    commission = calculate_toast_commission(price)
    amount_received = price - commission

    logger.info(
        f"Executing toast: sender={sender_id}, receiver={receiver_id}, "
        f"price={price}, commission={commission}, received={amount_received}"
    )

    # Списываем с отправителя
    spend_coins(
        db_session, game_id, sender_id, price, year,
        f"toast_to_{receiver_id}", auto_commit=False
    )

    # Начисляем получателю
    add_coins(
        db_session, game_id, receiver_id, amount_received, year,
        f"toast_from_{sender_id}", auto_commit=False
    )

    # Добавляем комиссию в банк
    bank = get_or_create_chat_bank(db_session, game_id)
    bank.balance += commission
    bank.updated_at = datetime.utcnow()
    db_session.add(bank)

    # Создаём запись о тосте
    toast = Toast(
        game_id=game_id,
        sender_id=sender_id,
        receiver_id=receiver_id,
        amount=price,
        commission=commission,
        year=year,
    )
    db_session.add(toast)

    db_session.commit()

    logger.info(
        f"Toast completed: {price} coins from {sender_id} to {receiver_id}, "
        f"commission {commission} to bank, game {game_id}, year {year}"
    )

    return price, amount_received, commission
