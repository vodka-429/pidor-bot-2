#!/usr/bin/env python3
"""Тестовый скрипт для проверки логирования"""

import logging

# Настраиваем логирование так же, как в main.py
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)-8s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Тестируем разные уровни логирования
logger.debug("DEBUG: Это отладочное сообщение")
logger.info("INFO: Это информационное сообщение")
logger.warning("WARNING: Это предупреждение")
logger.error("ERROR: Это ошибка")

# Тестируем логирование из модулей bot
bot_logger = logging.getLogger('bot.handlers.game.commands')
bot_logger.debug("DEBUG from bot.handlers.game.commands")
bot_logger.info("INFO from bot.handlers.game.commands")

print("\n✅ Если вы видите логи выше, то логирование работает корректно!")
