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
