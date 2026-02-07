"""Helper functions for shop functionality."""
import logging
from typing import List, Tuple
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.app.models import TGUser

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Константа для идентификации callback магазина
SHOP_CALLBACK_PREFIX = 'shop_'


def format_date_readable(year: int, day: int) -> str:
    """
    Форматировать year+day в читаемую дату.

    Args:
        year: Год
        day: День года (1-366)

    Returns:
        Строка вида "9 января" или "1 января 2027"
    """
    # Создаём дату из года и дня
    date_obj = datetime(year, 1, 1) + timedelta(days=day - 1)

    # Форматируем
    months_ru = [
        'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ]

    current_year = datetime.now().year
    if year == current_year:
        return f"{date_obj.day} {months_ru[date_obj.month - 1]}"
    else:
        return f"{date_obj.day} {months_ru[date_obj.month - 1]} {year}"


def format_shop_callback_data(item_type: str, owner_user_id: int) -> str:
    """
    Форматирует callback_data для кнопки магазина.

    Args:
        item_type: Тип товара ('immunity', 'double', 'predict')
        owner_user_id: ID владельца магазина (кто вызвал команду)

    Returns:
        Строка в формате 'shop_{item_type}_{owner_user_id}'
    """
    return f"{SHOP_CALLBACK_PREFIX}{item_type}_{owner_user_id}"


def parse_shop_callback_data(callback_data: str) -> Tuple[str, int]:
    """
    Парсит callback_data для получения item_type и owner_user_id.

    Args:
        callback_data: Строка callback_data в формате 'shop_{item_type}_{owner_user_id}'
                      или 'shop_{item_type}_confirm_{target_user_id}_{owner_user_id}'

    Returns:
        Кортеж (item_type, owner_user_id)

    Raises:
        ValueError: Если формат callback_data некорректен
    """
    logger.info(f"Parsing shop callback_data: {callback_data}")

    if not callback_data.startswith(SHOP_CALLBACK_PREFIX):
        raise ValueError(f"Invalid callback_data format: {callback_data}")

    # Убираем префикс и разделяем по '_'
    data = callback_data[len(SHOP_CALLBACK_PREFIX):]
    parts = data.split('_')

    logger.info(f"Callback data parts: {parts} (count: {len(parts)})")

    # Обрабатываем разные форматы callback_data
    if len(parts) == 2:
        # Формат: shop_{item_type}_{owner_user_id}
        try:
            item_type = parts[0]
            owner_user_id = int(parts[1])
            logger.info(f"Parsed as basic format: item_type={item_type}, owner_user_id={owner_user_id}")
            return item_type, owner_user_id
        except ValueError as e:
            raise ValueError(f"Invalid callback_data format: {callback_data}") from e

    elif len(parts) == 4 and parts[1] == 'confirm':
        # Формат: shop_{item_type}_confirm_{target_user_id}_{owner_user_id}
        try:
            item_type = parts[0]
            owner_user_id = int(parts[3])
            logger.info(f"Parsed as confirm format: item_type={item_type}, owner_user_id={owner_user_id}")
            return item_type, owner_user_id
        except ValueError as e:
            raise ValueError(f"Invalid callback_data format: {callback_data}") from e
    else:
        raise ValueError(f"Invalid callback_data format: {callback_data}")


def create_shop_keyboard(owner_user_id: int, game_id: int, active_effects: dict = None) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру магазина с кнопками товаров.

    Args:
        owner_user_id: ID владельца магазина (кто вызвал команду)
        game_id: ID игры (чата) для получения конфигурации
        active_effects: Словарь с информацией об активных эффектах

    Returns:
        InlineKeyboardMarkup с кнопками товаров
    """
    from bot.handlers.game.shop_service import get_shop_items

    items = get_shop_items(game_id)
    keyboard = []

    logger.info(f"Creating shop keyboard for owner_user_id: {owner_user_id}, game_id: {game_id}")

    for item in items:
        # Определяем, активен ли товар
        is_active = False
        if active_effects:
            if item['callback_data'] == 'shop_immunity' and active_effects.get('immunity_active'):
                is_active = True
            elif item['callback_data'] == 'shop_double' and active_effects.get('double_chance_bought_today'):
                is_active = True
            elif item['callback_data'] == 'shop_predict' and active_effects.get('prediction_exists'):
                is_active = True

        # Формируем текст кнопки с индикатором активности
        if is_active:
            button_text = f"✅ {item['name']} - {item['price']} 🪙"
        elif item['price'] is None:
            # Для действий без цены (передача, банк)
            button_text = item['name']
        else:
            button_text = f"{item['name']} - {item['price']} 🪙"

        # Создаём callback_data с типом товара и ID владельца
        callback_data = format_shop_callback_data(item['callback_data'].replace('shop_', ''), owner_user_id)

        logger.info(f"Created callback_data for {item['name']}: {callback_data}")

        button = InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        )

        # Каждая кнопка на отдельной строке
        keyboard.append([button])

    return InlineKeyboardMarkup(keyboard)


def create_prediction_keyboard(
    players: List[TGUser],
    owner_user_id: int,
    candidates_count: int,
    selected_ids: List[int] = None
) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора кандидатов для предсказания.

    Args:
        players: Список игроков (TGUser объекты)
        owner_user_id: ID владельца магазина (кто вызвал команду)
        candidates_count: Сколько кандидатов нужно выбрать
        selected_ids: Уже выбранные кандидаты (список ID)

    Returns:
        InlineKeyboardMarkup с кнопками игроков
    """
    selected_ids = selected_ids or []
    keyboard = []

    # Кнопка подтверждения в начале (активна только когда выбрано нужное количество)
    if len(selected_ids) == candidates_count:
        keyboard.append([InlineKeyboardButton(
            f"✅ Подтвердить ({candidates_count} кандидат{'а' if candidates_count < 5 else 'ов'})",
            callback_data=f"{SHOP_CALLBACK_PREFIX}predict_confirm_{owner_user_id}"
        )])
    else:
        remaining = candidates_count - len(selected_ids)
        keyboard.append([InlineKeyboardButton(
            f"⏳ Выберите ещё {remaining} кандидат{'а' if remaining < 5 else 'ов'}",
            callback_data="noop"
        )])

    row = []

    for player in players:
        # Формируем текст кнопки из имени пользователя
        button_text = player.first_name
        if player.last_name:
            button_text += f" {player.last_name}"

        # Отмечаем уже выбранных
        prefix = "✅ " if player.id in selected_ids else ""
        button_text = f"{prefix}{button_text}"

        # Создаём callback_data в формате shop_predict_select_{player_id}_{owner_user_id}
        callback_data = f"{SHOP_CALLBACK_PREFIX}predict_select_{player.id}_{owner_user_id}"

        button = InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        )

        row.append(button)

        # Если ряд заполнен (2 кнопки), добавляем его в клавиатуру
        if len(row) >= 2:
            keyboard.append(row)
            row = []

    # Добавляем оставшиеся кнопки
    if row:
        keyboard.append(row)

    # Кнопка отмены
    keyboard.append([InlineKeyboardButton(
        "❌ Отмена",
        callback_data=f"{SHOP_CALLBACK_PREFIX}cancel_{owner_user_id}"
    )])

    return InlineKeyboardMarkup(keyboard)


def create_double_chance_keyboard(players: List[TGUser], owner_user_id: int, callback_prefix: str = None) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора игрока для двойного шанса или передачи.

    Args:
        players: Список игроков (TGUser объекты)
        owner_user_id: ID владельца магазина (кто вызвал команду)
        callback_prefix: Префикс для callback_data (по умолчанию 'shop_double_confirm')

    Returns:
        InlineKeyboardMarkup с кнопками игроков
    """
    # Используем переданный префикс или дефолтный
    prefix = callback_prefix if callback_prefix else f"{SHOP_CALLBACK_PREFIX}double_confirm"

    keyboard = []
    row = []

    for player in players:
        # Формируем текст кнопки из имени пользователя
        button_text = player.first_name
        if player.last_name:
            button_text += f" {player.last_name}"

        # Создаём callback_data в формате {prefix}_{target_user_id}_{owner_user_id}
        callback_data = f"{prefix}_{player.id}_{owner_user_id}"

        button = InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        )

        row.append(button)

        # Если ряд заполнен (2 кнопки), добавляем его в клавиатуру
        if len(row) >= 2:
            keyboard.append(row)
            row = []

    # Добавляем оставшиеся кнопки
    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)


def create_transfer_amount_keyboard(balance: int, receiver_id: int, owner_user_id: int, game_id: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора суммы передачи.

    Args:
        balance: Баланс отправителя
        receiver_id: ID получателя (внутренний ID БД)
        owner_user_id: Telegram ID владельца магазина
        game_id: ID игры (чата) для получения конфигурации

    Returns:
        InlineKeyboardMarkup с кнопками выбора суммы
    """
    from bot.handlers.game.config import get_config

    config = get_config(game_id)
    keyboard = []

    # Рассчитываем суммы (только если >= transfer_min_amount)
    amounts = [
        (balance // 4, "25%"),
        (balance // 2, "50%"),
        (balance * 3 // 4, "75%"),
        (balance, "100%")
    ]

    row = []
    for amount, label in amounts:
        if amount >= config.constants.transfer_min_amount:
            callback_data = f"shop_transfer_amount_{receiver_id}_{amount}_{owner_user_id}"
            button = InlineKeyboardButton(
                text=f"{amount} 💰 ({label})",
                callback_data=callback_data
            )
            row.append(button)
            if len(row) >= 2:
                keyboard.append(row)
                row = []

    if row:
        keyboard.append(row)

    # Кнопка "Назад"
    keyboard.append([InlineKeyboardButton(
        "⬅️ Назад",
        callback_data=f"shop_back_{owner_user_id}"
    )])

    return InlineKeyboardMarkup(keyboard)


def format_shop_menu_message(balance: int, game_id: int, user_name: str = None, active_effects: dict = None) -> str:
    """
    Форматирует сообщение меню магазина с балансом и списком товаров.

    Args:
        balance: Текущий баланс пользователя
        game_id: ID игры (чата) для получения конфигурации
        user_name: Имя пользователя, чей это магазин (опционально)
        active_effects: Информация об активных эффектах

    Returns:
        Отформатированное сообщение в формате Markdown V2
    """
    from bot.utils import escape_markdown2, format_number
    from bot.handlers.game.shop_service import get_shop_items
    from bot.handlers.game.cbr_service import calculate_commission_percent

    # Получаем текущую ключевую ставку для отображения
    commission_rate = calculate_commission_percent()

    # Формируем заголовок с балансом и именем пользователя
    balance_str = format_number(balance)

    if user_name:
        user_name_escaped = escape_markdown2(user_name)
        header = f"🏪 *Магазин пидор\\-койнов*\n👤 Владелец: *{user_name_escaped}*\n\n💰 Баланс: *{balance_str}* 🪙\n\n"
    else:
        header = f"🏪 *Магазин пидор\\-койнов*\n\n💰 Ваш баланс: *{balance_str}* 🪙\n\n"

    # Добавляем информацию о комиссии
    commission_info = f"ℹ️ _Комиссия на покупки: {escape_markdown2(str(commission_rate))}% \\(ключевая ставка ЦБ РФ\\)_\n_Комиссия идёт в банк чата \\(минимум 1 🪙\\)_\n\n"

    # Формируем список товаров с информацией об активности
    items = get_shop_items(game_id)
    items_list = []

    for item in items:
        name_escaped = escape_markdown2(item['name'])
        desc_escaped = escape_markdown2(item['description'])

        # Добавляем информацию об активности
        status_info = ""
        if active_effects:
            if item['callback_data'] == 'shop_immunity' and active_effects.get('immunity_active'):
                date = active_effects.get('immunity_date', '')
                status_info = f"\n✅ _Активна на {escape_markdown2(date)}_"
            elif item['callback_data'] == 'shop_double' and active_effects.get('double_chance_bought_today'):
                status_info = "\n✅ _Уже куплен на завтра_"
            elif item['callback_data'] == 'shop_predict' and active_effects.get('prediction_exists'):
                status_info = "\n✅ _Предсказание создано_"

        # Проверяем, есть ли цена у товара
        if item['price'] is not None:
            price_str = format_number(item['price'])
            items_list.append(f"{name_escaped} \\- *{price_str}* 🪙\n_{desc_escaped}_{status_info}")
        else:
            items_list.append(f"{name_escaped}\n_{desc_escaped}_{status_info}")

    items_text = '\n\n'.join(items_list)

    # Формируем полное сообщение
    footer = "\n\n_Выберите товар для покупки:_"

    return header + commission_info + items_text + footer
