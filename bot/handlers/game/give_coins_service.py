"""Service functions for give coins button functionality."""
import logging
from typing import Tuple

from sqlmodel import select

from bot.app.models import GiveCoinsClick
from bot.handlers.game.coin_service import add_coins
from bot.handlers.game.config import get_config_by_game_id

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


def has_claimed_today(db_session, game_id: int, user_id: int, year: int, day: int) -> bool:
    """
    Проверить, получал ли игрок койны сегодня (по year+day).

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        year: Год
        day: День года (1-366)

    Returns:
        True если койны уже получены сегодня, False иначе
    """
    stmt = select(GiveCoinsClick).where(
        GiveCoinsClick.game_id == game_id,
        GiveCoinsClick.user_id == user_id,
        GiveCoinsClick.year == year,
        GiveCoinsClick.day == day
    )
    existing_click = db_session.exec(stmt).first()

    has_claimed = existing_click is not None
    logger.debug(f"User {user_id} has claimed coins today ({year}-{day}): {has_claimed}")
    return has_claimed


def claim_coins(
    db_session,
    game_id: int,
    user_id: int,
    year: int,
    day: int,
    is_winner: bool
) -> Tuple[bool, int]:
    """
    Получить койны за нажатие кнопки.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        year: Год
        day: День года (1-366)
        is_winner: Является ли пользователь пидором дня

    Returns:
        Кортеж (success, amount)
        success - True если койны успешно начислены, False если уже получены сегодня
        amount - количество начисленных койнов (0 если уже получены)

    Raises:
        ValueError: Если функция give_coins отключена для данного чата
    """
    # Получаем конфигурацию для чата
    config = get_config_by_game_id(db_session, game_id)

    # Проверяем, включена ли функция give_coins для этого чата
    if not config.constants.give_coins_enabled:
        raise ValueError("Give coins feature is disabled for this chat")

    # Проверяем, не получал ли уже сегодня
    if has_claimed_today(db_session, game_id, user_id, year, day):
        logger.info(f"User {user_id} already claimed coins today ({year}-{day})")
        return False, 0

    # Определяем количество койнов из конфигурации
    amount = (config.constants.give_coins_winner_amount if is_winner
              else config.constants.give_coins_amount)

    logger.info(
        f"Claiming coins: user={user_id}, game={game_id}, "
        f"is_winner={is_winner}, amount={amount}, {year}-{day}"
    )

    # Начисляем койны
    add_coins(
        db_session, game_id, user_id, amount, year,
        "give_coins_button", auto_commit=False
    )

    # Создаём запись о нажатии
    click = GiveCoinsClick(
        game_id=game_id,
        user_id=user_id,
        year=year,
        day=day,
        is_winner=is_winner,
        amount=amount
    )
    db_session.add(click)

    db_session.commit()

    logger.info(
        f"Coins claimed successfully: {amount} coins for user {user_id}, "
        f"game {game_id}, {year}-{day}"
    )

    return True, amount
