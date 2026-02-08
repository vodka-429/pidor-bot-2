"""Централизованный модуль конфигурации игры."""
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GameConstants:
    """Константы игры со значениями по умолчанию."""
    # Цены
    immunity_price: int = 10
    double_chance_price: int = 8
    prediction_price: int = 3
    reroll_price: int = 15

    # Награды
    coins_per_win: int = 4
    coins_per_command: int = 1
    self_pidor_multiplier: int = 2
    prediction_reward: int = 30
    give_coins_amount: int = 1
    give_coins_winner_amount: int = 2

    # Лимиты
    max_missed_days_for_final_voting: int = 10
    immunity_cooldown_days: int = 7
    transfer_min_amount: int = 2

    # Таймауты
    game_result_time_delay: int = 2
    reroll_timeout_minutes: int = 5

    # Feature flags - возможность отключать фичи для конкретных чатов
    reroll_enabled: bool = True
    transfer_enabled: bool = True
    prediction_enabled: bool = True
    immunity_enabled: bool = True
    double_chance_enabled: bool = True
    give_coins_enabled: bool = True


@dataclass
class ChatConfig:
    """Конфигурация конкретного чата."""
    chat_id: int
    enabled: bool = True
    is_test: bool = False
    constants: GameConstants = field(default_factory=GameConstants)


@dataclass
class GlobalConfig:
    """Глобальная конфигурация приложения."""
    # Список включённых чатов (замена CHAT_WHITELIST)
    enabled_chats: List[int] = field(default_factory=list)

    # ID тестового чата (замена TEST_CHAT_ID)
    test_chat_id: Optional[int] = None

    # Значения по умолчанию для всех чатов
    defaults: GameConstants = field(default_factory=GameConstants)

    # Переопределения для конкретных чатов
    chat_overrides: Dict[int, Dict[str, Any]] = field(default_factory=dict)


# Глобальный экземпляр конфигурации (ленивая инициализация)
_global_config: Optional[GlobalConfig] = None


def _load_global_config() -> GlobalConfig:
    """
    Загрузить глобальную конфигурацию из файла, путь к которому указан в GAME_CONFIG_PATH.

    Переменная окружения GAME_CONFIG_PATH должна содержать путь к JSON файлу с конфигурацией.

    Формат JSON файла:
    {
      "enabled_chats": [-1001392307997, -4608252738, -1002189152002, -1003671793100],
      "test_chat_id": -4608252738,
      "defaults": {
        "immunity_price": 10,
        "coins_per_win": 4
      },
      "chat_overrides": {
        "-4608252738": {
          "immunity_price": 5,
          "max_missed_days_for_final_voting": 100
        }
      }
    }

    Returns:
        GlobalConfig: Загруженная конфигурация
    """
    config_path = os.getenv('GAME_CONFIG_PATH', '')

    config_data = {}

    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            # Если не удалось прочитать файл, возвращаем пустую конфигурацию
            print(f"Warning: Failed to load config from {config_path}: {e}")
            config_data = {}
    else:
        # Если путь не указан или файл не существует, возвращаем пустую конфигурацию
        if config_path:
            print(f"Warning: Config file not found: {config_path}")

    # Извлекаем enabled_chats
    enabled_chats = config_data.get('enabled_chats', [])

    # Извлекаем test_chat_id
    test_chat_id = config_data.get('test_chat_id')

    # Создаём defaults из config_data
    defaults_data = config_data.get('defaults', {})
    defaults = GameConstants(**defaults_data)

    # Извлекаем chat_overrides
    # Ключи в JSON могут быть строками, конвертируем их в int
    chat_overrides_raw = config_data.get('chat_overrides', {})
    chat_overrides = {}
    for chat_id_str, overrides in chat_overrides_raw.items():
        try:
            chat_id = int(chat_id_str)
            chat_overrides[chat_id] = overrides
        except (ValueError, TypeError):
            # Пропускаем невалидные ключи
            continue

    return GlobalConfig(
        enabled_chats=enabled_chats,
        test_chat_id=test_chat_id,
        defaults=defaults,
        chat_overrides=chat_overrides
    )


def _get_global_config() -> GlobalConfig:
    """
    Получить глобальную конфигурацию (с ленивой инициализацией).

    Returns:
        GlobalConfig: Глобальная конфигурация
    """
    global _global_config
    if _global_config is None:
        _global_config = _load_global_config()
    return _global_config


def get_config(chat_id: int) -> ChatConfig:
    """
    Получить конфигурацию для конкретного чата с учётом переопределений.

    Args:
        chat_id: ID чата

    Returns:
        ChatConfig: Конфигурация чата с применёнными переопределениями
    """
    global_config = _get_global_config()

    # Проверяем, включён ли чат
    enabled = chat_id in global_config.enabled_chats

    # Проверяем, является ли чат тестовым
    is_test = (global_config.test_chat_id is not None and
               chat_id == global_config.test_chat_id)

    # Создаём копию констант по умолчанию
    constants_dict = {
        'immunity_price': global_config.defaults.immunity_price,
        'double_chance_price': global_config.defaults.double_chance_price,
        'prediction_price': global_config.defaults.prediction_price,
        'reroll_price': global_config.defaults.reroll_price,
        'coins_per_win': global_config.defaults.coins_per_win,
        'coins_per_command': global_config.defaults.coins_per_command,
        'self_pidor_multiplier': global_config.defaults.self_pidor_multiplier,
        'prediction_reward': global_config.defaults.prediction_reward,
        'give_coins_amount': global_config.defaults.give_coins_amount,
        'give_coins_winner_amount': global_config.defaults.give_coins_winner_amount,
        'max_missed_days_for_final_voting': global_config.defaults.max_missed_days_for_final_voting,
        'immunity_cooldown_days': global_config.defaults.immunity_cooldown_days,
        'transfer_min_amount': global_config.defaults.transfer_min_amount,
        'game_result_time_delay': global_config.defaults.game_result_time_delay,
        'reroll_timeout_minutes': global_config.defaults.reroll_timeout_minutes,
        'reroll_enabled': global_config.defaults.reroll_enabled,
        'transfer_enabled': global_config.defaults.transfer_enabled,
        'prediction_enabled': global_config.defaults.prediction_enabled,
        'immunity_enabled': global_config.defaults.immunity_enabled,
        'double_chance_enabled': global_config.defaults.double_chance_enabled,
        'give_coins_enabled': global_config.defaults.give_coins_enabled,
    }

    # Применяем переопределения для конкретного чата
    if chat_id in global_config.chat_overrides:
        overrides = global_config.chat_overrides[chat_id]
        for key, value in overrides.items():
            if key in constants_dict:
                constants_dict[key] = value

    # Создаём объект GameConstants с применёнными переопределениями
    constants = GameConstants(**constants_dict)

    return ChatConfig(
        chat_id=chat_id,
        enabled=enabled,
        is_test=is_test,
        constants=constants
    )


def get_enabled_chats() -> List[int]:
    """
    Получить список включённых чатов.

    Returns:
        List[int]: Список ID включённых чатов
    """
    config = _get_global_config()
    return config.enabled_chats


def get_test_chat_id() -> Optional[int]:
    """
    Получить ID тестового чата.

    Returns:
        Optional[int]: ID тестового чата или None, если не задано
    """
    config = _get_global_config()
    return config.test_chat_id


def is_test_chat(chat_id: int) -> bool:
    """
    Проверить, является ли чат тестовым.

    Args:
        chat_id: ID чата для проверки

    Returns:
        bool: True если чат тестовый, False иначе
    """
    test_id = get_test_chat_id()
    return test_id is not None and chat_id == test_id


def get_config_by_game_id(db_session, game_id: int) -> ChatConfig:
    """
    Получить конфигурацию для чата по game_id (внутреннему ID игры в БД).

    Эта функция объединяет получение chat_id из БД и вызов get_config()
    в одну операцию для удобства использования в сервисах, которые
    работают с game_id, а не chat_id.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (внутренний ID в БД)

    Returns:
        ChatConfig: Конфигурация чата с применёнными переопределениями

    Raises:
        ValueError: Если игра не найдена
    """
    from sqlmodel import select
    from bot.app.models import Game

    stmt = select(Game).where(Game.id == game_id)
    game = db_session.exec(stmt).first()
    if game is None:
        raise ValueError(f"Game with id {game_id} not found")

    return get_config(game.chat_id)
