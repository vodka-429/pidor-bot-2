#!/usr/bin/env python3
"""Тестовый скрипт для проверки получения обновлений ботом"""

import logging
import os
from dotenv import load_dotenv
from telegram.ext import Updater, CallbackQueryHandler

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)-8s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загружаем токен
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_API_SECRET", "")


def test_callback_handler(update, context):
    """Тестовый обработчик callback"""
    logger.info("🎯 TEST CALLBACK HANDLER CALLED!")
    logger.info(f"Callback data: {update.callback_query.data}")
    logger.info(f"User: {update.callback_query.from_user.id}")

    # Отвечаем на callback
    update.callback_query.answer("✅ Тестовый обработчик сработал!")


def main():
    logger.info("Starting test bot...")

    updater = Updater(API_TOKEN)
    dp = updater.dispatcher

    # Регистрируем тестовый обработчик для ВСЕХ callback
    logger.info("Registering test callback handler for ALL callbacks")
    dp.add_handler(CallbackQueryHandler(test_callback_handler))
    logger.info("Handler registered")

    # Запускаем бота
    updater.start_polling()
    logger.info("Bot started. Press Ctrl+C to stop.")
    logger.info("Now try clicking any button in the bot...")

    updater.idle()


if __name__ == '__main__':
    main()
