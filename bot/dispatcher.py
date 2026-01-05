import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, filters, \
    CallbackQueryHandler, InlineQueryHandler, MessageHandler, \
    ChatJoinRequestHandler, PollHandler

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

from bot.handlers.about.commands import about_cmd
from bot.handlers.db.handlers import open_db_session, \
    tg_user_middleware_handler, close_db_session_handler
from bot.handlers.game.commands import pidor_cmd, pidorules_cmd, pidoreg_cmd, \
    pidorunreg_cmd, pidorstats_cmd, pidorall_cmd, pidorme_cmd, \
    pidoryearresults_cmd, pidoregmany_cmd, pidormissed_cmd, pidorfinal_cmd, \
    pidorfinalstatus_cmd, handle_vote_callback, pidorfinalclose_cmd, \
    pidorcoinsme_cmd, pidorcoinsstats_cmd, pidorcoinsall_cmd
from bot.handlers.kvstore.commands import get_cmd, set_cmd, del_cmd, list_cmd
from bot.handlers.meme.commands import meme_cmd, memeru_cmd, \
    meme_refresh_callback, memeru_refresh_callback, meme_save_callback, \
    memeru_save_callback
from bot.handlers.meme.text_callback import MEME_REFRESH, MEMERU_REFRESH, \
    MEME_SAVE, MEMERU_SAVE
from bot.handlers.misc.commands import hello_cmd, echo_cmd, slap_cmd, me_cmd, \
    shrug_cmd, google_cmd, pin_message_cmd, text_inline_cmd
from bot.handlers.misc.error import bot_error_handler
from bot.handlers.tiktok.commands import tt_video_cmd, tt_depersonalize_cmd, \
    tt_inline_cmd
from bot.utils import chat_whitelist


# TODO: Refactor this function to automatically scan for handlers ending with
#  '_cmd' in the bot/handlers folder
def init_dispatcher(application: Application, db_engine):
    """Register handlers."""
    logger.info("=== INITIALIZING DISPATCHER ===")
    chats = chat_whitelist()
    logger.info(f"Chat whitelist: {chats}")
    if chats:
        ne = ~filters.UpdateType.EDITED_MESSAGE & filters.Chat(chats)
    else:
        ne = ~filters.UpdateType.EDITED_MESSAGE

    # Middlewares setup
    # В v20+ используем MessageHandler с filters.ALL для middleware
    # Также добавляем middleware для CallbackQueryHandler
    application.add_handler(MessageHandler(filters.ALL, open_db_session(db_engine)), group=-100)
    application.add_handler(CallbackQueryHandler(open_db_session(db_engine)), group=-100)

    application.add_handler(MessageHandler(filters.ALL, tg_user_middleware_handler), group=-99)
    application.add_handler(CallbackQueryHandler(tg_user_middleware_handler), group=-99)

    application.add_handler(MessageHandler(filters.ALL, close_db_session_handler), group=100)
    application.add_handler(CallbackQueryHandler(close_db_session_handler), group=100)

    # About handler
    # dp.add_handler(CommandHandler('about', about_cmd, filters=ne))

    # Tiktok handlers
    # dp.add_handler(CommandHandler('ttvideo', tt_video_cmd, filters=ne))
    # dp.add_handler(CommandHandler('ttlink', tt_depersonalize_cmd, filters=ne))
    # dp.add_handler(InlineQueryHandler(tt_inline_cmd, pattern=r'https://.+tiktok\.com.+'))

    # Meme handlers
    # dp.add_handler(CommandHandler('meme', meme_cmd, filters=ne))
    # dp.add_handler(CallbackQueryHandler(meme_save_callback, pattern=MEME_SAVE))
    # dp.add_handler(
    #     CallbackQueryHandler(meme_refresh_callback, pattern=MEME_REFRESH))
    # dp.add_handler(CommandHandler('memeru', memeru_cmd, filters=ne))
    # dp.add_handler(
    #     CallbackQueryHandler(memeru_save_callback, pattern=MEMERU_SAVE))
    # dp.add_handler(
    #     CallbackQueryHandler(memeru_refresh_callback, pattern=MEMERU_REFRESH))

    # Game handlers
    application.add_handler(CommandHandler('pidor', pidor_cmd, filters=ne))
    application.add_handler(MessageHandler(filters.Regex(r'/pidor\d\d\d\d(?:@.+)?') & ne, pidoryearresults_cmd))
    application.add_handler(
        CommandHandler('pidorules', pidorules_cmd, filters=ne))
    application.add_handler(CommandHandler('pidoreg', pidoreg_cmd, filters=ne))
    application.add_handler(CommandHandler('pidoregmany', pidoregmany_cmd, filters=ne))
    application.add_handler(CommandHandler('pidorunreg', pidorunreg_cmd, filters=ne))
    application.add_handler(CommandHandler('pidorstats', pidorstats_cmd, filters=ne))
    application.add_handler(CommandHandler('pidorall', pidorall_cmd, filters=ne))
    application.add_handler(CommandHandler('pidorme', pidorme_cmd, filters=ne))
    application.add_handler(CommandHandler('pidormissed', pidormissed_cmd, filters=ne))
    application.add_handler(CommandHandler('pidorfinal', pidorfinal_cmd, filters=ne))
    application.add_handler(CommandHandler('pidorfinalstatus', pidorfinalstatus_cmd, filters=ne))
    application.add_handler(CommandHandler('pidorfinalclose', pidorfinalclose_cmd, filters=ne))

    # PidorCoin handlers
    application.add_handler(CommandHandler('pidorcoinsme', pidorcoinsme_cmd, filters=ne))
    application.add_handler(CommandHandler('pidorcoinsstats', pidorcoinsstats_cmd, filters=ne))
    application.add_handler(CommandHandler('pidorcoinsall', pidorcoinsall_cmd, filters=ne))

    # Регистрируем CallbackQueryHandler для голосования
    # В python-telegram-bot v21+ CallbackQueryHandler не поддерживает filters параметр
    # Фильтрация чатов должна выполняться внутри обработчика
    application.add_handler(CallbackQueryHandler(handle_vote_callback, pattern=r'^vote_'))

    # Key-Value storage handlers
    application.add_handler(CommandHandler('get', get_cmd, filters=ne))
    application.add_handler(CommandHandler('list', list_cmd, filters=ne))
    application.add_handler(CommandHandler('set', set_cmd, filters=ne))
    application.add_handler(CommandHandler('del', del_cmd, filters=ne))

    # Misc handlers
    # dp.add_handler(CommandHandler("hello", hello_cmd, filters=ne))
    # dp.add_handler(CommandHandler("echo", echo_cmd, filters=ne))
    # dp.add_handler(CommandHandler('slap', slap_cmd, filters=ne))
    # dp.add_handler(CommandHandler('me', me_cmd, filters=ne))
    # dp.add_handler(CommandHandler('shrug', shrug_cmd, filters=ne))
    # dp.add_handler(CommandHandler('google', google_cmd, filters=ne))
    # dp.add_handler(CommandHandler('pin', pin_message_cmd, filters=ne))
    # dp.add_handler(InlineQueryHandler(text_inline_cmd))

    application.add_error_handler(bot_error_handler)
