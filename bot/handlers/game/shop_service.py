"""Service functions for working with the pidor coins shop."""
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlmodel import select

from bot.app.models import GamePlayerEffect, Prediction, PidorCoinTransaction
from bot.utils import to_date

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Цены товаров в магазине
IMMUNITY_PRICE = 10
DOUBLE_CHANCE_PRICE = 5
PREDICTION_PRICE = 15

# Награда за правильное предсказание
PREDICTION_REWARD = 30

# Кулдаун защиты (дней)
IMMUNITY_COOLDOWN_DAYS = 7


def get_or_create_player_effects(db_session, game_id: int, user_id: int) -> GamePlayerEffect:
    """
    Получить или создать запись эффектов игрока в конкретной игре.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя

    Returns:
        Запись GamePlayerEffect для игрока в игре
    """
    stmt = select(GamePlayerEffect).where(
        GamePlayerEffect.game_id == game_id,
        GamePlayerEffect.user_id == user_id
    )

    effect = db_session.exec(stmt).first()

    if effect is None:
        effect = GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            next_win_multiplier=1
        )
        db_session.add(effect)
        db_session.commit()
        db_session.refresh(effect)
        logger.info(f"Created new player effects for user {user_id} in game {game_id}")

    return effect


def spend_coins(db_session, game_id: int, user_id: int, amount: int, year: int, reason: str, auto_commit: bool = True) -> PidorCoinTransaction:
    """
    Списать койны у пользователя (создать отрицательную транзакцию).

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        amount: Количество койнов для списания (положительное число)
        year: Год транзакции
        reason: Причина списания
        auto_commit: Автоматически коммитить транзакцию (по умолчанию True)

    Returns:
        Созданная транзакция PidorCoinTransaction с отрицательным amount
    """
    if amount <= 0:
        raise ValueError("Amount must be positive")

    # Создаем транзакцию с отрицательным значением
    transaction = PidorCoinTransaction(
        game_id=game_id,
        user_id=user_id,
        amount=-amount,  # Отрицательное значение для списания
        year=year,
        reason=reason
    )

    db_session.add(transaction)

    if auto_commit:
        db_session.commit()
        db_session.refresh(transaction)

    logger.info(f"Spent {amount} coins from user {user_id} in game {game_id} for year {year}, reason: {reason}")

    return transaction


def can_afford(db_session, game_id: int, user_id: int, price: int) -> bool:
    """
    Проверить, достаточно ли у пользователя койнов для покупки.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        price: Цена товара

    Returns:
        True если достаточно средств, False иначе
    """
    from bot.handlers.game.coin_service import get_balance

    balance = get_balance(db_session, game_id, user_id)
    return balance >= price


def get_shop_items() -> List[Dict[str, any]]:
    """
    Получить список доступных товаров в магазине.

    Returns:
        Список словарей с информацией о товарах:
        - name: название товара
        - price: цена в койнах
        - description: описание товара
        - callback_data: данные для callback кнопки
    """
    return [
        {
            'name': '🛡️ Защита от пидора',
            'price': IMMUNITY_PRICE,
            'description': 'Защита на 1 день (кулдаун 7 дней)',
            'callback_data': 'shop_immunity'
        },
        {
            'name': '🎲 Двойной шанс',
            'price': DOUBLE_CHANCE_PRICE,
            'description': 'Удвоенный шанс стать пидором на 1 день',
            'callback_data': 'shop_double'
        },
        {
            'name': '🔮 Предсказание',
            'price': PREDICTION_PRICE,
            'description': 'Предскажи пидора дня (+30 койнов при успехе)',
            'callback_data': 'shop_predict'
        }
    ]


def buy_immunity(db_session, game_id: int, user_id: int, year: int, current_date: date) -> tuple[bool, str]:
    """
    Купить защиту от пидора.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        year: Текущий год
        current_date: Текущая дата

    Returns:
        Кортеж (успех, сообщение об ошибке или успехе)
    """
    # Проверяем баланс
    if not can_afford(db_session, game_id, user_id, IMMUNITY_PRICE):
        return False, "insufficient_funds"

    # Получаем или создаем запись эффектов
    effect = get_or_create_player_effects(db_session, game_id, user_id)

    # Проверяем, не активна ли уже защита
    immunity_date = to_date(effect.immunity_until)
    if immunity_date and immunity_date >= current_date:
        logger.debug(f"Immunity already active until {immunity_date}")
        return False, "already_active"

    # Проверяем кулдаун (7 дней с последнего использования)
    last_used_date = to_date(effect.immunity_last_used)
    if last_used_date:
        cooldown_end = last_used_date + timedelta(days=IMMUNITY_COOLDOWN_DAYS)
        logger.debug(f"Checking cooldown: last_used={last_used_date}, cooldown_end={cooldown_end}, current={current_date}")
        if current_date < cooldown_end:
            return False, f"cooldown:{cooldown_end.isoformat()}"

    # Списываем койны
    spend_coins(db_session, game_id, user_id, IMMUNITY_PRICE, year, "shop_immunity", auto_commit=False)

    # Активируем защиту на завтра
    effect.immunity_until = current_date + timedelta(days=1)
    effect.immunity_last_used = current_date

    db_session.commit()

    logger.info(f"User {user_id} bought immunity in game {game_id} until {effect.immunity_until}")

    return True, "success"


def buy_double_chance(db_session, game_id: int, user_id: int, target_user_id: int, year: int, current_date: date) -> tuple[bool, str]:
    """
    Купить двойной шанс стать пидором для указанного игрока.
    Несколько игроков могут купить двойной шанс одному игроку, увеличивая его шансы.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя, который покупает
        target_user_id: ID игрока, для которого покупается двойной шанс
        year: Текущий год
        current_date: Текущая дата

    Returns:
        Кортеж (успех, сообщение об ошибке или успехе)
    """
    # Проверяем баланс покупателя
    if not can_afford(db_session, game_id, user_id, DOUBLE_CHANCE_PRICE):
        return False, "insufficient_funds"

    # Получаем или создаем запись эффектов для целевого игрока
    effect = get_or_create_player_effects(db_session, game_id, target_user_id)

    # Списываем койны у покупателя
    spend_coins(db_session, game_id, user_id, DOUBLE_CHANCE_PRICE, year, f"shop_double_chance_for_{target_user_id}", auto_commit=False)

    # Активируем двойной шанс на завтра для целевого игрока
    # Не проверяем, активен ли уже - можно покупать несколько раз для увеличения шансов
    effect.double_chance_until = current_date + timedelta(days=1)
    effect.double_chance_bought_by = user_id

    db_session.commit()

    logger.info(f"User {user_id} bought double chance for user {target_user_id} in game {game_id} until {effect.double_chance_until}")

    return True, "success"


def create_prediction(db_session, game_id: int, user_id: int, predicted_user_id: int, year: int, day: int) -> tuple[bool, str]:
    """
    Создать предсказание пидора дня.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя (кто предсказывает)
        predicted_user_id: ID предсказываемого пользователя
        year: Год предсказания
        day: День предсказания

    Returns:
        Кортеж (успех, сообщение об ошибке или успехе)
    """
    # Проверяем, что пользователь не предсказывает себя
    if user_id == predicted_user_id:
        return False, "self_prediction"

    # Проверяем баланс
    if not can_afford(db_session, game_id, user_id, PREDICTION_PRICE):
        return False, "insufficient_funds"

    # Проверяем, нет ли уже предсказания на этот день
    stmt = select(Prediction).where(
        Prediction.game_id == game_id,
        Prediction.user_id == user_id,
        Prediction.year == year,
        Prediction.day == day
    )
    existing_prediction = db_session.exec(stmt).first()

    if existing_prediction:
        return False, "already_exists"

    # Списываем койны
    spend_coins(db_session, game_id, user_id, PREDICTION_PRICE, year, "shop_prediction", auto_commit=False)

    # Создаем предсказание
    prediction = Prediction(
        game_id=game_id,
        user_id=user_id,
        predicted_user_id=predicted_user_id,
        year=year,
        day=day,
        is_correct=None
    )

    db_session.add(prediction)
    db_session.commit()

    logger.info(f"User {user_id} created prediction for user {predicted_user_id} in game {game_id} for day {year}-{day}")

    return True, "success"
