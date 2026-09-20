import asyncio
import logging
from datetime import datetime
from functools import wraps

from sqlalchemy.exc import DisconnectionError, OperationalError
from sqlmodel import Session
from telegram import Update
from telegram.ext import ContextTypes

from bot.app.models import TGUser
from bot.utils import ECallbackContext

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


def retry_on_db_error(max_retries=3, delay=1, backoff=2):
    """
    Декоратор для автоматического повтора при ошибках БД с exponential backoff
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (DisconnectionError, OperationalError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (backoff ** attempt)
                        logger.warning(f"DB connection error on attempt {attempt + 1}/{max_retries}: {e}. Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"DB connection failed after {max_retries} attempts: {e}")
                        raise
                except Exception as e:
                    # Для других ошибок не делаем retry
                    logger.error(f"Non-DB error in {func.__name__}: {e}")
                    raise
            raise last_exception
        return wrapper
    return decorator


@retry_on_db_error(max_retries=3, delay=1, backoff=2)
async def tg_user_middleware_handler(update: Update, context: ECallbackContext):
    # Логируем тип обновления для отладки
    update_type = "unknown"
    if update.message:
        update_type = "message"
        message = update.message
        reply_to = message.reply_to_message
        command = None
        if message.text and message.text.startswith('/'):
            command = message.text.split(maxsplit=1)[0]
        if command or reply_to is not None:
            logger.info(
                "MESSAGE_RECEIVED update_id=%s chat_id=%s user_id=%s "
                "message_id=%s command=%s reply_to_message_id=%s reply_to_bot=%s",
                update.update_id,
                update.effective_chat.id if update.effective_chat else None,
                update.effective_user.id if update.effective_user else None,
                message.message_id,
                command,
                reply_to.message_id if reply_to else None,
                bool(
                    reply_to
                    and reply_to.from_user
                    and reply_to.from_user.id == context.bot.id
                ),
            )
    elif update.callback_query:
        update_type = f"callback_query (data: {update.callback_query.data})"
        logger.info(
            "CALLBACK_RECEIVED update_id=%s chat_id=%s user_id=%s data=%s",
            update.update_id,
            update.effective_chat.id if update.effective_chat else None,
            update.callback_query.from_user.id,
            update.callback_query.data,
        )
    elif update.edited_message:
        update_type = "edited_message"
    
    logger.debug(f"tg_user_middleware_handler: Processing {update_type}")

    session = context.db_session
    tg_user: TGUser = session.query(TGUser).filter_by(
        tg_id=update.effective_user.id).one_or_none()
    if tg_user is None:
        tg_user = TGUser(tg_id=update.effective_user.id,
                         username=update.effective_user.username,
                         first_name=update.effective_user.first_name,
                         last_name=update.effective_user.last_name,
                         lang_code=update.effective_user.language_code)
    else:
        updated = False
        if tg_user.username != update.effective_user.username:
            tg_user.username = update.effective_user.username
            updated = True
        if tg_user.first_name != update.effective_user.first_name:
            tg_user.first_name = update.effective_user.first_name
            updated = True
        if tg_user.last_name != update.effective_user.last_name:
            tg_user.last_name = update.effective_user.last_name
            updated = True
        if update.effective_user.language_code is not None \
                and tg_user.lang_code != update.effective_user.language_code:
            tg_user.lang_code = update.effective_user.language_code
            updated = True
        if updated:
            tg_user.updated_at = datetime.utcnow()

    tg_user.last_seen_at = datetime.utcnow()
    session.add(tg_user)
    session.commit()
    session.refresh(tg_user)
    context.tg_user = tg_user


async def tg_user_from_text(user, update: Update, context: ECallbackContext):
    session = context.db_session
    tg_user: TGUser = session.query(TGUser).filter_by(
        tg_id=user.id).one_or_none()
    if tg_user is None:
        tg_user = TGUser(tg_id=user.id,
                         username=user.username,
                         first_name=user.first_name,
                         last_name=user.last_name,
                         lang_code=user.language_code)
    else:
        updated = False
        if tg_user.username != user.username:
            tg_user.username = user.username
            updated = True
        if tg_user.first_name != user.first_name:
            tg_user.first_name = user.first_name
            updated = True
        if tg_user.last_name != user.last_name:
            tg_user.last_name = user.last_name
            updated = True
        if user.language_code is not None \
                and tg_user.lang_code != user.language_code:
            tg_user.lang_code = user.language_code
            updated = True
        if updated:
            tg_user.updated_at = datetime.utcnow()

    tg_user.last_seen_at = datetime.utcnow()
    session.add(tg_user)
    session.commit()
    session.refresh(tg_user)
    context.tg_user = tg_user


def open_db_session(db):
    async def open_db_session_handler(update: Update, context: ECallbackContext):
        # Логируем открытие сессии для отладки
        update_type = "unknown"
        if update.message:
            update_type = "message"
        elif update.callback_query:
            update_type = f"callback_query (data: {update.callback_query.data})"
        elif update.edited_message:
            update_type = "edited_message"

        logger.debug(f"open_db_session_handler: Opening session for {update_type}")

        session = Session(db)
        context.db_session = session
    return open_db_session_handler


async def close_db_session_handler(update: Update, context: ECallbackContext):
    context.db_session.close()
