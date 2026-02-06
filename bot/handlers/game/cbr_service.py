"""Service functions for working with CBR (Central Bank of Russia) key rate."""
import logging
import re
from datetime import datetime, timedelta
from typing import Optional
import requests

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Константы для работы с ключевой ставкой ЦБ РФ
CBR_MAIN_PAGE_URL = "https://cbr.ru"
FALLBACK_COMMISSION_PERCENT = 10.0
CACHE_DURATION_HOURS = 1
MIN_COMMISSION = 1

# Кэш для ключевой ставки
_cached_rate: Optional[float] = None
_cache_timestamp: Optional[datetime] = None


def _is_cache_valid() -> bool:
    """
    Проверить, валиден ли кэш ключевой ставки.

    Returns:
        True если кэш валиден (не старше CACHE_DURATION_HOURS), False иначе
    """
    if _cached_rate is None or _cache_timestamp is None:
        return False

    time_since_cache = datetime.utcnow() - _cache_timestamp
    return time_since_cache < timedelta(hours=CACHE_DURATION_HOURS)


def _fetch_key_rate_from_api() -> Optional[float]:
    """
    Получить ключевую ставку с главной страницы сайта ЦБ РФ.

    Парсит HTML главной страницы cbr.ru и извлекает значение ключевой ставки
    из текста "Ключевая ставка".

    Returns:
        Ключевая ставка в процентах или None при ошибке
    """
    try:
        logger.info(f"Fetching key rate from CBR main page: {CBR_MAIN_PAGE_URL}")

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        response = requests.get(CBR_MAIN_PAGE_URL, headers=headers, timeout=5.0)
        response.raise_for_status()

        # Ищем текст "Ключевая ставка" и берем ближайшие цифры после него
        # Формат: "Ключевая ставка ... 16,00" или "Ключевая ставка ... 16.00"
        match = re.search(r'Ключевая ставка.*?(\d+[,\.]\d{2})', response.text, re.DOTALL)

        if match:
            # Меняем запятую на точку для float: "16,00" -> "16.00"
            rate_str = match.group(1).replace(',', '.')
            rate = float(rate_str)
            logger.info(f"Successfully fetched key rate from CBR main page: {rate}%")
            return rate
        else:
            logger.warning("Could not find key rate on CBR main page")
            return None

    except requests.RequestException as e:
        logger.error(f"HTTP error while fetching key rate: {e}")
        return None
    except (ValueError, AttributeError) as e:
        logger.error(f"Error parsing key rate from page: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while fetching key rate: {e}")
        return None


def get_key_rate() -> float:
    """
    Получить ключевую ставку ЦБ РФ с кэшированием.

    Сначала проверяет кэш. Если кэш устарел или пуст, делает запрос к API.
    При ошибке API возвращает fallback значение.

    Returns:
        Ключевая ставка в процентах (например, 21.0 для 21%)
    """
    global _cached_rate, _cache_timestamp

    # Проверяем кэш
    if _is_cache_valid():
        logger.debug(f"Using cached key rate: {_cached_rate}%")
        return _cached_rate

    # Пытаемся получить свежую ставку
    rate = _fetch_key_rate_from_api()

    if rate is not None:
        # Обновляем кэш
        _cached_rate = rate
        _cache_timestamp = datetime.utcnow()
        logger.info(f"Updated key rate cache: {rate}%")
        return rate

    # Fallback: используем кэшированное значение, если оно есть
    if _cached_rate is not None:
        logger.warning(f"API failed, using stale cached rate: {_cached_rate}%")
        return _cached_rate

    # Fallback: используем фиксированное значение
    logger.warning(f"API failed and no cache, using fallback rate: {FALLBACK_COMMISSION_PERCENT}%")
    return FALLBACK_COMMISSION_PERCENT


def calculate_commission_percent() -> float:
    """
    Получить процент комиссии (равен ключевой ставке ЦБ РФ).

    Returns:
        Процент комиссии (например, 21.0 для 21%)
    """
    return get_key_rate()


def calculate_commission_amount(price: int) -> int:
    """
    Рассчитать сумму комиссии для конкретной цены.

    Комиссия рассчитывается как процент от цены, округляется вниз,
    но не может быть меньше MIN_COMMISSION.

    Args:
        price: Цена покупки в койнах

    Returns:
        Сумма комиссии в койнах (минимум MIN_COMMISSION)

    Examples:
        При ставке 21%:
        - price=10 → commission=2 (10 * 0.21 = 2.1 → 2)
        - price=8 → commission=1 (8 * 0.21 = 1.68 → 1)
        - price=3 → commission=1 (3 * 0.21 = 0.63 → 0, но минимум 1)
    """
    if price <= 0:
        raise ValueError("Price must be positive")

    commission_percent = calculate_commission_percent()
    commission = int(price * commission_percent / 100)

    # Применяем минимальную комиссию
    result = max(commission, MIN_COMMISSION)

    logger.debug(
        f"Calculated commission for price {price}: {result} coins "
        f"(rate: {commission_percent}%, raw: {commission})"
    )

    return result
