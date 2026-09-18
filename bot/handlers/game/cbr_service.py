"""Service functions for working with CBR (Central Bank of Russia) key rate."""
import logging
import re
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Optional
import requests

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Константы для работы с ключевой ставкой ЦБ РФ
CBR_KEY_RATE_URL = "https://www.cbr.ru/hd_base/KeyRate/"
FALLBACK_COMMISSION_PERCENT = 10.0
CACHE_DURATION_HOURS = 1
MIN_COMMISSION = 1

# Кэш для ключевой ставки
_cached_rate: Optional[float] = None
_cache_timestamp: Optional[datetime] = None


class _KeyRateTableParser(HTMLParser):
    """Collect table rows without depending on the CBR page's CSS markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._table_depth = 0
        self._current_table = None
        self._current_row = None
        self._current_cell = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == 'table':
            if self._table_depth == 0:
                self._current_table = []
            self._table_depth += 1
        elif self._table_depth == 1 and tag == 'tr':
            self._current_row = []
        elif self._table_depth == 1 and tag in ('td', 'th') and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data):
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self._table_depth == 1 and tag in ('td', 'th') and self._current_cell is not None:
            cell_text = ' '.join(''.join(self._current_cell).split())
            self._current_row.append(cell_text)
            self._current_cell = None
        elif self._table_depth == 1 and tag == 'tr' and self._current_row is not None:
            self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == 'table' and self._table_depth:
            self._table_depth -= 1
            if self._table_depth == 0:
                self.tables.append(self._current_table)
                self._current_table = None


def _parse_key_rate_html(html: str) -> Optional[tuple[float, str]]:
    """Extract ``(rate, date)`` from the CBR Date/Rate table."""
    parser = _KeyRateTableParser()
    parser.feed(html)

    for table in parser.tables:
        for header_index, row in enumerate(table):
            normalized = [cell.casefold() for cell in row]
            if 'дата' not in normalized or 'ставка' not in normalized:
                continue

            date_index = normalized.index('дата')
            rate_index = normalized.index('ставка')
            for data_row in table[header_index + 1:]:
                if max(date_index, rate_index) >= len(data_row):
                    continue

                rate_date = data_row[date_index]
                rate_text = data_row[rate_index]
                if not re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', rate_date):
                    continue
                if not re.fullmatch(r'\d{1,2},\d{2}', rate_text):
                    continue

                rate = float(rate_text.replace(',', '.'))
                if 0 < rate <= 100:
                    return rate, rate_date

    return None


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
    Получить ключевую ставку со страницы истории ставок ЦБ РФ.

    Парсит HTML страницы hd_base/KeyRate/ и извлекает значение ключевой ставки
    из первой строки таблицы (актуальная ставка всегда первая).

    Returns:
        Ключевая ставка в процентах или None при ошибке
    """
    try:
        logger.info(f"Fetching key rate from CBR key rate page: {CBR_KEY_RATE_URL}")

        # Обязательно притворяемся браузером (иначе ЦБ может разорвать соединение)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        response = requests.get(CBR_KEY_RATE_URL, headers=headers, timeout=10.0)
        response.raise_for_status()

        parsed_rate = _parse_key_rate_html(response.text)

        if parsed_rate:
            rate, rate_date = parsed_rate
            logger.info(
                f"Successfully fetched key rate from CBR key rate page: "
                f"{rate}% for {rate_date}"
            )
            return rate
        else:
            logger.warning("Could not find key rate on CBR key rate page")
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
