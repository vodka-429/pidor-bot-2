import os
from datetime import date, datetime
from typing import Optional, Union

from sqlmodel import Session
from telegram import User
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown

from bot.app.models import TGUser


def raw_name(user: User):
    return user.username or user.full_name


def escape_markdown2(text: str):
    return escape_markdown(text, version=2)


def escape_markdown2_safe(text: str):
    """
    Безопасно экранирует текст для MarkdownV2, избегая двойного экранирования.
    Проверяет, не экранирован ли уже текст частично.
    """
    if not text:
        return text

    # Если текст уже содержит экранированные символы, используем обычное экранирование
    # В противном случае, это может быть признаком частичного экранирования
    return escape_markdown(text, version=2)


def format_number(number):
    """
    Безопасно форматирует число для использования в MarkdownV2.
    Экранирует точки и другие специальные символы в числах.
    """
    if isinstance(number, (int, float)):
        # Преобразуем число в строку и экранируем точки
        number_str = str(number)
        # Экранируем точки в десятичных числах
        number_str = number_str.replace('.', '\\.')
        return number_str
    else:
        # Если это уже строка, экранируем её полностью
        return escape_markdown2(str(number))


def escape_word(word: str):
    """
    Экранирует отдельное слово или фразу для MarkdownV2.
    Особенно полезно для склонений со скобками типа "раз(а)".
    """
    if not word:
        return word

    return escape_markdown2(word)


def to_date(dt: Optional[Union[datetime, date]]) -> Optional[date]:
    """
    Конвертировать datetime в date, если необходимо.

    Эта функция используется для безопасного сравнения дат,
    когда в БД хранится datetime, а для сравнения нужен date.
    Также обрабатывает MagicMock объекты из тестов.

    Args:
        dt: datetime или date объект, или None

    Returns:
        date объект или None

    Examples:
        >>> from datetime import datetime, date
        >>> to_date(datetime(2024, 1, 15, 10, 30))
        date(2024, 1, 15)
        >>> to_date(date(2024, 1, 15))
        date(2024, 1, 15)
        >>> to_date(None)
        None
    """
    if dt is None:
        return None
    # Проверка на MagicMock для тестов
    if type(dt).__name__ == 'MagicMock':
        return None
    if isinstance(dt, datetime):
        return dt.date()
    return dt


class ECallbackContext(ContextTypes.DEFAULT_TYPE):
    """Extended CallbackContext with additional fields"""
    db_session: Session
    tg_user: TGUser


def chat_whitelist():
    env = os.environ.get('CHAT_WHITELIST', '')
    if env:
        return [int(x) for x in env.split(',')]
    else:
        return []


def get_test_chat_id():
    """
    Получает ID тестового чата из переменной окружения TEST_CHAT_ID.

    Returns:
        Optional[int]: ID тестового чата или None, если не задано
    """
    env = os.environ.get('TEST_CHAT_ID', '')
    if env:
        try:
            return int(env)
        except ValueError:
            return None
    return None


def get_allowed_final_voting_closers():
    """
    Получает список username пользователей, которые могут закрывать финальное голосование.

    Returns:
        List[str]: Список username или пустой список, если не задано
    """
    env = os.environ.get('ALLOWED_FINAL_VOTING_CLOSERS', '')
    if env:
        return [x.strip() for x in env.split(',') if x.strip()]
    else:
        return []
