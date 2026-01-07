"""Helper functions for shop functionality."""
import logging
from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.app.models import TGUser

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Константа для идентификации callback магазина
SHOP_CALLBACK_PREFIX = 'shop_'


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

    Returns:
        Кортеж (item_type, owner_user_id)

    Raises:
        ValueError: Если формат callback_data некорректен
    """
    if not callback_data.startswith(SHOP_CALLBACK_PREFIX):
        raise ValueError(f"Invalid callback_data format: {callback_data}")

    # Убираем префикс и разделяем по '_'
    data = callback_data[len(SHOP_CALLBACK_PREFIX):]
    parts = data.split('_')

    if len(parts) != 2:
        raise ValueError(f"Invalid callback_data format: {callback_data}")

    try:
        item_type = parts[0]
        owner_user_id = int(parts[1])
    except ValueError as e:
        raise ValueError(f"Invalid callback_data format: {callback_data}") from e

    return item_type, owner_user_id


def create_shop_keyboard(owner_user_id: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру магазина с кнопками товаров.

    Args:
        owner_user_id: ID владельца магазина (кто вызвал команду)

    Returns:
        InlineKeyboardMarkup с кнопками товаров
    """
    from bot.handlers.game.shop_service import get_shop_items

    items = get_shop_items()
    keyboard = []

    for item in items:
        # Формируем текст кнопки с названием и ценой
        button_text = f"{item['name']} - {item['price']} 🪙"

        # Создаём callback_data с типом товара и ID владельца
        callback_data = format_shop_callback_data(item['callback_data'].replace('shop_', ''), owner_user_id)

        button = InlineKeyboardButton(
            text=button_text,
            callback_data=callback_data
        )

        # Каждая кнопка на отдельной строке
        keyboard.append([button])

    return InlineKeyboardMarkup(keyboard)


def create_prediction_keyboard(players: List[TGUser], owner_user_id: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора игрока для предсказания.

    Args:
        players: Список игроков (TGUser объекты)
        owner_user_id: ID владельца магазина (кто вызвал команду)

    Returns:
        InlineKeyboardMarkup с кнопками игроков
    """
    keyboard = []
    row = []

    for player in players:
        # Формируем текст кнопки из имени пользователя
        button_text = player.first_name
        if player.last_name:
            button_text += f" {player.last_name}"

        # Создаём callback_data в формате shop_predict_confirm_{predicted_user_id}_{owner_user_id}
        callback_data = f"{SHOP_CALLBACK_PREFIX}predict_confirm_{player.id}_{owner_user_id}"

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


def create_double_chance_keyboard(players: List[TGUser], owner_user_id: int) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру для выбора игрока для двойного шанса.

    Args:
        players: Список игроков (TGUser объекты)
        owner_user_id: ID владельца магазина (кто вызвал команду)

    Returns:
        InlineKeyboardMarkup с кнопками игроков
    """
    keyboard = []
    row = []

    for player in players:
        # Формируем текст кнопки из имени пользователя
        button_text = player.first_name
        if player.last_name:
            button_text += f" {player.last_name}"

        # Создаём callback_data в формате shop_double_confirm_{target_user_id}_{owner_user_id}
        callback_data = f"{SHOP_CALLBACK_PREFIX}double_confirm_{player.id}_{owner_user_id}"

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


def format_shop_menu_message(balance: int) -> str:
    """
    Форматирует сообщение меню магазина с балансом и списком товаров.

    Args:
        balance: Текущий баланс пользователя

    Returns:
        Отформатированное сообщение в формате Markdown V2
    """
    from bot.utils import escape_markdown2, format_number
    from bot.handlers.game.shop_service import get_shop_items

    # Формируем заголовок с балансом
    balance_str = format_number(balance)
    header = f"🏪 *Магазин пидор\\-койнов*\n\n💰 Ваш баланс: *{balance_str}* 🪙\n\n"

    # Формируем список товаров
    items = get_shop_items()
    items_list = []

    for item in items:
        price_str = format_number(item['price'])
        name_escaped = escape_markdown2(item['name'])
        desc_escaped = escape_markdown2(item['description'])
        items_list.append(f"{name_escaped} \\- *{price_str}* 🪙\n_{desc_escaped}_")

    items_text = '\n\n'.join(items_list)

    # Формируем полное сообщение
    footer = "\n\n_Выберите товар для покупки:_"

    return header + items_text + footer
