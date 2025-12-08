import logging
import os.path
from os import getenv

import sentry_sdk
import telegram.ext
from dotenv import load_dotenv
from sqlmodel import create_engine
from telegram.ext import Updater

from bot.dispatcher import init_dispatcher

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)-8s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Явно добавляем handler для stdout
    ]
)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Устанавливаем уровень логирования для telegram библиотеки
logging.getLogger('telegram').setLevel(logging.INFO)
logging.getLogger('telegram.ext').setLevel(logging.INFO)
logging.getLogger('telegram.bot').setLevel(logging.INFO)

# Наши логи должны быть на уровне DEBUG
logging.getLogger('bot').setLevel(logging.DEBUG)
logging.getLogger('__main__').setLevel(logging.DEBUG)

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
    uri = dburi.replace("postgres://", "postgresql://", 1)
engine = create_engine(dburi, echo=False)

updater = Updater(API_TOKEN, persistence=telegram.ext.PicklePersistence(
    filename='storage/data.bin'))
dispatch = updater.dispatcher

# Setup dispatcher
init_dispatcher(updater.dispatcher, engine)

# Run the bot
updater.start_polling()
logger.info(f"https://t.me/{updater.bot.get_me()['username']} started")
updater.idle()
