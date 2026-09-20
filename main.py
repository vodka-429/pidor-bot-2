import asyncio
from contextlib import suppress
import logging
import os.path
from os import getenv

import sentry_sdk
from dotenv import load_dotenv
from sqlmodel import create_engine
from telegram.ext import Application
from telegram.request import HTTPXRequest

from bot.dispatcher import init_dispatcher
from bot.chat_migration import migrate_configured_chat_ids
from bot.handlers.game.config import get_chat_migrations
from bot.polling_health import (
    TrackedHTTPXRequest,
    WatchedSequentialUpdateProcessor,
    polling_watchdog,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)-8s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Явно добавляем handler для stdout
    ]
)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# HTTPX and python-telegram-bot include the Bot API token and full updates in
# verbose log messages. Keep third-party loggers quiet in production.
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

# Application logs retain useful operational context without flooding kubelet
# log rotation with request-level transport details.
logging.getLogger('bot').setLevel(logging.INFO)
logging.getLogger('__main__').setLevel(logging.INFO)

# Load configs and create bot instance
load_dotenv()  # load telegram bot token from .env file
API_TOKEN = getenv("TELEGRAM_BOT_API_SECRET", "")
if not os.path.exists('storage'):
    os.mkdir('storage')

sentry_sdk.init(
    dsn=getenv("SENTRY_DSN", ""),
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0
)

dburi = os.getenv("DATABASE_URL", "Error no db url provided")  # or other relevant config var
if dburi and dburi.startswith("postgres://"):
    dburi = dburi.replace("postgres://", "postgresql://", 1)
engine = create_engine(dburi, echo=False)


async def main():
    """Main function to run the bot."""
    migrate_configured_chat_ids(engine, get_chat_migrations())
    update_processor = WatchedSequentialUpdateProcessor()
    builder = (
        Application.builder()
        .token(API_TOKEN)
        .concurrent_updates(update_processor)
    )
    proxy = getenv("BOT_HTTPS_PROXY")
    request_kwargs = {
        "connect_timeout": 20.0,
        "read_timeout": 30.0,
    }
    polling_request_kwargs = {
        "connect_timeout": 20.0,
        "read_timeout": 40.0,
    }
    if proxy:
        logger.info("Using outbound proxy for Telegram API")
        request_kwargs["proxy"] = proxy
        polling_request_kwargs["proxy"] = proxy

    polling_request = TrackedHTTPXRequest(**polling_request_kwargs)
    builder = (
        builder
        .request(HTTPXRequest(**request_kwargs))
        .get_updates_request(polling_request)
    )
    application = builder.build()
    
    # Setup dispatcher
    init_dispatcher(application, engine)
    
    # Run the bot
    # ВАЖНО: Явно указываем allowed_updates для получения callback_query
    logger.info(f"Starting bot polling...")
    logger.info("Bot will receive updates: message, callback_query, inline_query, poll, poll_answer")
    
    # Initialize and start polling
    await application.initialize()
    await application.start()
    
    # Get bot info
    bot_info = await application.bot.get_me()
    logger.info(f"https://t.me/{bot_info.username} started")
    logger.info("Bot is polling with allowed_updates: message, callback_query, inline_query, poll, poll_answer")
    
    # Start polling with specified allowed_updates
    await application.updater.start_polling(
        allowed_updates=["message", "callback_query", "inline_query", "poll", "poll_answer"]
    )

    watchdog_task = asyncio.create_task(
        polling_watchdog(polling_request),
        name="telegram-polling-watchdog",
    )
    
    # Run until stopped
    try:
        # Keep the bot running
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Received stop signal")
    finally:
        watchdog_task.cancel()
        with suppress(asyncio.CancelledError):
            await watchdog_task
        # Cleanup
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
