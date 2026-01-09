"""Service functions for working with the pidor coins shop."""
import logging
from datetime import date, datetime, timedelta
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


def is_leap_year(year: int) -> bool:
    """Проверить, является ли год високосным."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def get_days_in_year(year: int) -> int:
    """Получить количество дней в году."""
    return 366 if is_leap_year(year) else 365


def calculate_next_day(current_date: date, year: int) -> tuple[int, int]:
    """
    Вычислить следующий день (year, day) для эффекта.

    Args:
        current_date: Текущая дата
        year: Текущий год

    Returns:
        Кортеж (год, день года) для следующего дня
    """
    current_day = current_date.timetuple().tm_yday
    next_day = current_day + 1
    days_in_year = get_days_in_year(year)

    if next_day > days_in_year:
        return year + 1, 1
    else:
        return year, next_day


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
    """Купить защиту от пидора. Защита действует на СЛЕДУЮЩИЙ день."""
    # Проверяем баланс
    if not can_afford(db_session, game_id, user_id, IMMUNITY_PRICE):
        return False, "insufficient_funds"

    effect = get_or_create_player_effects(db_session, game_id, user_id)

    # Вычисляем завтрашний день (день действия защиты)
    target_year, target_day = calculate_next_day(current_date, year)

    # Проверяем, не активна ли уже защита на завтра
    if effect.immunity_year == target_year and effect.immunity_day == target_day:
        logger.debug(f"Immunity already active for {target_year}-{target_day}")
        return False, f"already_active:{target_year}:{target_day}"

    # Проверяем кулдаун (7 дней с последнего использования)
    if effect.immunity_last_used:
        # immunity_last_used это datetime, нужно преобразовать в date
        last_used_date = effect.immunity_last_used.date() if isinstance(effect.immunity_last_used, datetime) else effect.immunity_last_used
        cooldown_end = last_used_date + timedelta(days=IMMUNITY_COOLDOWN_DAYS)
        if current_date < cooldown_end:
            return False, f"cooldown:{cooldown_end.isoformat()}"

    # Списываем койны
    spend_coins(db_session, game_id, user_id, IMMUNITY_PRICE, year, "shop_immunity", auto_commit=False)

    # Устанавливаем защиту на завтра
    effect.immunity_year = target_year
    effect.immunity_day = target_day
    effect.immunity_last_used = current_date

    db_session.commit()

    logger.info(f"User {user_id} bought immunity in game {game_id} for {target_year}-{target_day}")
    return True, "success"


def buy_double_chance(db_session, game_id: int, user_id: int, target_user_id: int, year: int, current_date: date) -> tuple[bool, str]:
    """
    Купить двойной шанс стать пидором для указанного игрока.

    Двойной шанс действует на СЛЕДУЮЩИЙ день после покупки.
    Один покупатель может купить только один двойной шанс в день.
    Несколько игроков могут купить двойной шанс одному игроку.
    """
    from bot.app.models import DoubleChancePurchase

    # Проверяем баланс
    if not can_afford(db_session, game_id, user_id, DOUBLE_CHANCE_PRICE):
        return False, "insufficient_funds"

    # Вычисляем завтрашний день (день действия)
    target_year, target_day = calculate_next_day(current_date, year)

    # Проверяем, не покупал ли уже этот игрок двойной шанс на завтра
    stmt = select(DoubleChancePurchase).where(
        DoubleChancePurchase.game_id == game_id,
        DoubleChancePurchase.buyer_id == user_id,
        DoubleChancePurchase.year == target_year,
        DoubleChancePurchase.day == target_day
    )
    existing_purchase = db_session.exec(stmt).first()

    if existing_purchase:
        return False, "already_bought_today"

    # Списываем койны
    spend_coins(db_session, game_id, user_id, DOUBLE_CHANCE_PRICE, year,
               f"shop_double_chance_for_{target_user_id}", auto_commit=False)

    # Создаём запись о покупке
    purchase = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=user_id,
        target_id=target_user_id,
        year=target_year,
        day=target_day,
        is_used=False
    )
    db_session.add(purchase)
    db_session.commit()

    logger.info(f"User {user_id} bought double chance for user {target_user_id} in game {game_id} for {target_year}-{target_day}")
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


def get_active_effects(db_session, game_id: int, user_id: int, current_date: date) -> dict:
    """
    Получить информацию об активных эффектах пользователя.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры
        user_id: ID пользователя
        current_date: Текущая дата

    Returns:
        Словарь с ключами:
        - immunity_active: bool - активна ли защита на завтра
        - immunity_date: str - дата действия защиты (если активна)
        - double_chance_bought_today: bool - куплен ли двойной шанс на завтра
        - prediction_exists: bool - есть ли предсказание на завтра
    """
    from bot.app.models import DoubleChancePurchase, Prediction

    effect = get_or_create_player_effects(db_session, game_id, user_id)

    # Вычисляем завтрашний день
    current_year = current_date.year
    target_year, target_day = calculate_next_day(current_date, current_year)

    # Проверяем защиту (активна на завтра)
    immunity_active = (effect.immunity_year == target_year and effect.immunity_day == target_day)
    immunity_date = None
    if immunity_active:
        from bot.handlers.game.shop_helpers import format_date_readable
        immunity_date = format_date_readable(effect.immunity_year, effect.immunity_day)

    # Проверяем покупку двойного шанса на завтра
    stmt = select(DoubleChancePurchase).where(
        DoubleChancePurchase.game_id == game_id,
        DoubleChancePurchase.buyer_id == user_id,
        DoubleChancePurchase.year == target_year,
        DoubleChancePurchase.day == target_day
    )
    double_chance_bought_today = db_session.exec(stmt).first() is not None

    # Проверяем предсказание на завтра
    stmt = select(Prediction).where(
        Prediction.game_id == game_id,
        Prediction.user_id == user_id,
        Prediction.year == target_year,
        Prediction.day == target_day
    )
    prediction_exists = db_session.exec(stmt).first() is not None

    return {
        'immunity_active': immunity_active,
        'immunity_date': immunity_date,
        'double_chance_bought_today': double_chance_bought_today,
        'prediction_exists': prediction_exists
    }
