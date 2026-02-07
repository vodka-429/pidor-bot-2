"""Централизованный модуль конфигурации игры."""
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GameConstants:
    """
    Константы игры со значениями по умолчанию.

    Этот класс содержит все настраиваемые параметры игры, включая цены,
    награды, лимиты и feature flags для включения/отключения функций.

    Attributes:
        Цены в магазине (в пидоркоинах):
            immunity_price: Цена защиты от выбора пидором (по умолчанию: 10)
            double_chance_price: Цена двойного шанса стать пидором (по умолчанию: 8)
            prediction_price: Цена создания предсказания (по умолчанию: 3)
            reroll_price: Цена перевыбора пидора дня (по умолчанию: 15)

        Награды (в пидоркоинах):
            coins_per_win: Награда за победу в игре (по умолчанию: 4)
            coins_per_command: Награда за использование команды (по умолчанию: 1)
            self_pidor_multiplier: Множитель награды при самовыборе (по умолчанию: 2)
            prediction_reward: Награда за правильное предсказание (по умолчанию: 30)
            give_coins_amount: Количество койнов для раздачи обычным игрокам (по умолчанию: 1)
            give_coins_winner_amount: Количество койнов для раздачи победителю (по умолчанию: 2)

        Лимиты:
            max_missed_days_for_final_voting: Максимальное количество пропущенных дней
                для проведения финального голосования (по умолчанию: 10)
            immunity_cooldown_days: Период ожидания между покупками защиты в днях (по умолчанию: 7)
            transfer_min_amount: Минимальная сумма для перевода койнов (по умолчанию: 2)

        Таймауты:
            game_result_time_delay: Задержка перед показом результата игры в секундах (по умолчанию: 2)
            reroll_timeout_minutes: Время действия кнопки перевыбора в минутах (по умолчанию: 5)

        Feature flags (включение/отключение функций):
            reroll_enabled: Включить функцию перевыбора пидора (по умолчанию: True)
            transfer_enabled: Включить функцию перевода койнов между игроками (по умолчанию: True)
            prediction_enabled: Включить функцию предсказаний (по умолчанию: True)
            immunity_enabled: Включить функцию защиты от выбора (по умолчанию: True)
            double_chance_enabled: Включить функцию двойного шанса (по умолчанию: True)
            give_coins_enabled: Включить функцию раздачи койнов (по умолчанию: True)

    Example:
        >>> constants = GameConstants(immunity_price=5, reroll_enabled=False)
        >>> print(constants.immunity_price)  # 5
        >>> print(constants.coins_per_win)  # 4 (значение по умолчанию)
    """
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
    """
    Конфигурация конкретного чата.

    Содержит настройки для отдельного чата, включая его статус (включен/выключен),
    является ли он тестовым, и специфичные для него константы игры.

    Attributes:
        chat_id: Уникальный идентификатор чата в Telegram
        enabled: Флаг, указывающий, включен ли бот для этого чата (по умолчанию: True)
        is_test: Флаг, указывающий, является ли чат тестовым (по умолчанию: False)
            Тестовые чаты могут иметь специальные настройки для отладки
        constants: Константы игры для этого чата с учетом переопределений

    Example:
        >>> config = ChatConfig(chat_id=-123456, enabled=True, is_test=False)
        >>> print(config.constants.immunity_price)  # 10 (значение по умолчанию)
    """
    chat_id: int
    enabled: bool = True
    is_test: bool = False
    constants: GameConstants = field(default_factory=GameConstants)


@dataclass
class GlobalConfig:
    """
    Глобальная конфигурация приложения.

    Содержит общие настройки для всех чатов, включая список разрешенных чатов,
    тестовый чат, значения по умолчанию и переопределения для конкретных чатов.

    Attributes:
        enabled_chats: Список ID чатов, в которых бот активен (whitelist).
            Замена для переменной окружения CHAT_WHITELIST.
            Пример: [-1001392307997, -4608252738, -1002189152002]

        test_chat_id: ID чата, используемого для тестирования.
            Замена для переменной окружения TEST_CHAT_ID.
            В тестовом чате могут быть включены специальные функции для отладки.
            Пример: -4608252738

        defaults: Значения констант по умолчанию для всех чатов.
            Эти значения используются, если для конкретного чата не заданы переопределения.

        chat_overrides: Словарь переопределений констант для конкретных чатов.
            Ключ - ID чата, значение - словарь с переопределяемыми параметрами.
            Пример: {
                -4608252738: {"immunity_price": 5, "reroll_enabled": False},
                -1001392307997: {"max_missed_days_for_final_voting": 100}
            }

    Example:
        >>> config = GlobalConfig(
        ...     enabled_chats=[-123456, -789012],
        ...     test_chat_id=-123456,
        ...     defaults=GameConstants(immunity_price=10),
        ...     chat_overrides={-123456: {"immunity_price": 5}}
        ... )
    """
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


def _load_config_from_file(config_path: str) -> GlobalConfig:
    """
    Загрузить конфигурацию из JSON-файла.

    Args:
        config_path: Путь к файлу конфигурации

    Returns:
        GlobalConfig: Загруженная конфигурация

    Raises:
        FileNotFoundError: Если файл не найден
        json.JSONDecodeError: Если файл содержит невалидный JSON
    """
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, 'r', encoding='utf-8') as f:
        config_data = json.load(f)

    # Создаём дефолтные константы
    defaults_data = config_data.get('defaults', {})
    defaults = GameConstants(**{k: v for k, v in defaults_data.items() if hasattr(GameConstants, k)})

    # Парсим переопределения для чатов
    chat_overrides_raw = config_data.get('chat_overrides', {})
    chat_overrides = {}
    for chat_id_str, overrides in chat_overrides_raw.items():
        try:
            chat_id = int(chat_id_str)
            chat_overrides[chat_id] = overrides
        except ValueError:
            logger.warning(f"Invalid chat_id in chat_overrides: {chat_id_str}")

    # Создаём глобальную конфигурацию
    global_config = GlobalConfig(
        enabled_chats=config_data.get('enabled_chats', []),
        test_chat_id=config_data.get('test_chat_id'),
        defaults=defaults,
        chat_overrides=chat_overrides
    )

    logger.info(f"Loaded config from {config_path}: {len(global_config.enabled_chats)} enabled chats, test_chat_id={global_config.test_chat_id}")

    return global_config


def _load_config_from_env() -> GlobalConfig:
    """
    Загрузить конфигурацию из переменной окружения GAME_CONFIG.

    Переменная окружения GAME_CONFIG должна содержать путь к JSON-файлу с конфигурацией.
    Если переменная не задана или файл не найден, используются значения по умолчанию.

    Формат JSON-файла:
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
        },
        "-1001392307997": {
          "reroll_enabled": false,
          "transfer_enabled": false
        }
      }
    }

    Returns:
        GlobalConfig: Загруженная конфигурация
    """
    config_path = os.getenv('GAME_CONFIG')

    if not config_path:
        logger.warning("GAME_CONFIG environment variable not set, using default configuration")
        return GlobalConfig()

    try:
        return _load_config_from_file(config_path)
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}, using default configuration")
        return GlobalConfig()
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse config file {config_path}: {e}, using default configuration")
        return GlobalConfig()
    except Exception as e:
        logger.error(f"Unexpected error loading config from {config_path}: {e}, using default configuration")
        return GlobalConfig()


def _get_global_config() -> GlobalConfig:
    """
    Получить глобальную конфигурацию (с ленивой инициализацией).

    Returns:
        GlobalConfig: Глобальная конфигурация
    """
    global _global_config

    if _global_config is None:
        _global_config = _load_config_from_env()

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
    is_test = global_config.test_chat_id is not None and chat_id == global_config.test_chat_id

    # Создаём копию дефолтных констант
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
                logger.debug(f"Applied override for chat {chat_id}: {key}={value}")

    # Создаём объект констант с переопределениями
    constants = GameConstants(**constants_dict)

    # Создаём конфигурацию чата
    chat_config = ChatConfig(
        chat_id=chat_id,
        enabled=enabled,
        is_test=is_test,
        constants=constants
    )

    return chat_config


def get_enabled_chats() -> List[int]:
    """
    Получить список включённых чатов.

    Замена для функции chat_whitelist() из bot/utils.py.

    Returns:
        List[int]: Список ID включённых чатов
    """
    config = _get_global_config()
    return config.enabled_chats


def get_test_chat_id() -> Optional[int]:
    """
    Получить ID тестового чата.

    Замена для функции get_test_chat_id() из bot/utils.py.

    Returns:
        Optional[int]: ID тестового чата или None, если не задано
    """
    config = _get_global_config()
    return config.test_chat_id


def is_test_chat(chat_id: int) -> bool:
    """
    Проверить, является ли чат тестовым.

    Замена для функции is_test_chat() из bot/handlers/game/voting_helpers.py.

    Args:
        chat_id: ID чата для проверки

    Returns:
        bool: True если чат тестовый, False иначе
    """
    test_id = get_test_chat_id()
    return test_id is not None and chat_id == test_id
