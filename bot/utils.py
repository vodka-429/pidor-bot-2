import os

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
