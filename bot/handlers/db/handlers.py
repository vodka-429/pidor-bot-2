import logging
from datetime import datetime

from sqlmodel import Session
from telegram import Update
from telegram.ext import ContextTypes

from bot.app.models import TGUser
from bot.utils import ECallbackContext

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


async def tg_user_middleware_handler(update: Update, context: ECallbackContext):
    # Логируем тип обновления для отладки
    update_type = "unknown"
    if update.message:
        update_type = "message"
    elif update.callback_query:
        update_type = f"callback_query (data: {update.callback_query.data})"
        logger.info(f"🔔 CALLBACK_QUERY RECEIVED: {update.callback_query.data} from user {update.callback_query.from_user.id}")
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
