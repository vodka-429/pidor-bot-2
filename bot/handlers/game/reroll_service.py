"""Service functions for reroll (перевыборы) functionality."""
import asyncio
import logging
import random
from datetime import date
from typing import List, Tuple

from sqlmodel import select

from bot.app.models import GameResult, TGUser
from bot.handlers.game.coin_service import add_coins
from bot.handlers.game.shop_service import spend_coins, can_afford
from bot.handlers.game.config import get_config_by_game_id
from bot.handlers.game.selection_service import SelectionResult

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


def can_reroll(db_session, game_id: int, year: int, day: int) -> bool:
    """
    Проверить, доступен ли перевыбор для данного дня.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        year: Год игры
        day: День года (1-366)

    Returns:
        True если перевыбор доступен, False иначе
    """
    stmt = select(GameResult).where(
        GameResult.game_id == game_id,
        GameResult.year == year,
        GameResult.day == day
    )
    game_result = db_session.exec(stmt).first()

    if game_result is None:
        logger.warning(f"GameResult not found for game {game_id}, {year}-{day}")
        return False

    is_available = game_result.reroll_available
    logger.debug(f"Reroll available for {year}-{day}: {is_available}")
    return is_available


def execute_reroll(
    db_session,
    game_id: int,
    year: int,
    day: int,
    initiator_id: int,
    players: List[TGUser],
    current_date: date,
    immunity_enabled: bool = True
) -> Tuple[TGUser, TGUser, SelectionResult]:
    """
    Выполнить перевыбор.

    ВАЖНО: Первый победитель СОХРАНЯЕТ свои койны!
    Новый победитель тоже получает койны.
    Оба победителя получают награду.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        year: Год игры
        day: День года (1-366)
        initiator_id: ID пользователя, инициировавшего перевыбор
        players: Список всех игроков для перевыбора
        current_date: Текущая дата для проверки эффектов
        immunity_enabled: Включена ли защита (по умолчанию True)

    Returns:
        Кортеж (старый_победитель, новый_победитель, selection_result)
        где selection_result содержит метаданные о выборе (защита, двойной шанс)

    Raises:
        ValueError: Если GameResult не найден или игроки пусты, или если reroll отключен
    """
    if not players:
        raise ValueError("Players list cannot be empty")

    # Получаем конфигурацию для чата
    config = get_config_by_game_id(db_session, game_id)

    # Проверяем, включены ли перевыборы
    if not config.constants.reroll_enabled:
        raise ValueError("Reroll is disabled for this chat")

    # Получаем результат игры
    stmt = select(GameResult).where(
        GameResult.game_id == game_id,
        GameResult.year == year,
        GameResult.day == day
    )
    game_result = db_session.exec(stmt).first()

    if game_result is None:
        raise ValueError(f"GameResult not found for game {game_id}, {year}-{day}")

    # Получаем старого победителя
    old_winner_id = game_result.winner_id
    stmt = select(TGUser).where(TGUser.id == old_winner_id)
    old_winner = db_session.exec(stmt).first()

    if old_winner is None:
        raise ValueError(f"Old winner with id {old_winner_id} not found")

    # Получаем цену перевыбора из конфигурации
    reroll_price = config.constants.reroll_price

    # Списываем койны с инициатора
    spend_coins(db_session, game_id, initiator_id, reroll_price, year, "reroll", auto_commit=False)
    logger.info(f"Spent {reroll_price} coins from user {initiator_id} for reroll")

    # ВАЖНО: НЕ отменяем награду старого победителя!
    # Он сохраняет свои койны.

    # Выбираем нового победителя с учётом эффектов (защита, двойной шанс)
    from bot.handlers.game.selection_service import select_winner_with_effects

    selection_result = select_winner_with_effects(
        db_session, game_id, players, current_date, immunity_enabled
    )

    # Если все игроки защищены - выбираем случайного (fallback)
    if selection_result.all_protected:
        logger.warning(f"All players protected during reroll in game {game_id}, selecting random")
        new_winner = random.choice(players)
    else:
        new_winner = selection_result.winner

    logger.info(f"Selected new winner: {new_winner.id} ({new_winner.full_username()})")

    # Получаем награду за победу из конфигурации
    coins_per_win = config.constants.coins_per_win

    # Если сработала защита при перевыборе - начисляем койны защищённому игроку
    if selection_result.had_immunity and selection_result.protected_player:
        protected_player = selection_result.protected_player
        add_coins(db_session, game_id, protected_player.id, coins_per_win, year, "immunity_save_reroll", auto_commit=False)
        logger.info(f"Protection activated during reroll for player {protected_player.id}, awarded {coins_per_win} coins")

    # Обновляем GameResult
    game_result.original_winner_id = old_winner_id
    game_result.winner_id = new_winner.id
    game_result.reroll_available = False
    game_result.reroll_initiator_id = initiator_id

    db_session.add(game_result)

    # Начисляем койны новому победителю (даже если это тот же человек - двойная награда!)
    add_coins(db_session, game_id, new_winner.id, coins_per_win, year, "pidor_win_reroll", auto_commit=False)
    logger.info(f"Added {coins_per_win} coins to new winner {new_winner.id}")

    # Обрабатываем предсказания для нового победителя
    from bot.handlers.game.prediction_service import process_predictions_for_reroll

    predictions_results = process_predictions_for_reroll(
        db_session, game_id, year, day, new_winner.id
    )
    logger.info(f"Processed {len(predictions_results)} predictions for reroll")

    db_session.commit()

    logger.info(
        f"Reroll executed: old winner {old_winner_id}, new winner {new_winner.id}, "
        f"initiator {initiator_id} in game {game_id} for {year}-{day}"
    )

    return old_winner, new_winner, selection_result


async def remove_reroll_button_after_timeout(
    bot,
    chat_id: int,
    message_id: int,
    delay_minutes: int | None = None
):
    """
    Удалить кнопку перевыбора через указанное время.

    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        message_id: ID сообщения с кнопкой
        delay_minutes: Задержка в минутах (если None, берётся из конфигурации)
    """
    # Если задержка не указана, получаем из конфигурации
    if delay_minutes is None:
        from bot.handlers.game.config import get_config
        config = get_config(chat_id)
        delay_minutes = config.constants.reroll_timeout_minutes

    await asyncio.sleep(delay_minutes * 60)
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None
        )
        logger.info(f"Removed reroll button from message {message_id} in chat {chat_id}")
    except Exception as e:
        # Сообщение могло быть удалено или кнопка уже убрана
        logger.debug(f"Could not remove reroll button: {e}")
