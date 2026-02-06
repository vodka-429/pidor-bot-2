"""Tests for CBR (Central Bank of Russia) service."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import requests

from bot.handlers.game.cbr_service import (
    get_key_rate,
    calculate_commission_percent,
    calculate_commission_amount,
    _is_cache_valid,
    _fetch_key_rate_from_api,
    FALLBACK_COMMISSION_PERCENT,
    MIN_COMMISSION,
)


@pytest.mark.unit
class TestFetchKeyRateFromAPI:
    """Тесты получения ключевой ставки с сайта ЦБ РФ."""

    def test_fetch_success_comma_format(self):
        """Успешное получение ставки (формат с запятой: 21,00)."""
        mock_response = MagicMock()
        mock_response.text = '<html><body>Ключевая ставка составляет 21,00%</body></html>'
        mock_response.raise_for_status = MagicMock()

        with patch('requests.get', return_value=mock_response):
            rate = _fetch_key_rate_from_api()
            assert rate == 21.0

    def test_fetch_success_dot_format(self):
        """Успешное получение ставки (формат с точкой: 21.00)."""
        mock_response = MagicMock()
        mock_response.text = '<html><body>Ключевая ставка составляет 21.00%</body></html>'
        mock_response.raise_for_status = MagicMock()

        with patch('requests.get', return_value=mock_response):
            rate = _fetch_key_rate_from_api()
            assert rate == 21.0

    def test_fetch_success_with_html_tags(self):
        """Успешное получение ставки с HTML тегами между текстом."""
        mock_response = MagicMock()
        mock_response.text = '<html><body><div>Ключевая ставка</div><span>16,00</span></body></html>'
        mock_response.raise_for_status = MagicMock()

        with patch('requests.get', return_value=mock_response):
            rate = _fetch_key_rate_from_api()
            assert rate == 16.0

    def test_fetch_http_error(self):
        """Ошибка HTTP при запросе."""
        with patch('requests.get', side_effect=requests.RequestException("Network error")):
            rate = _fetch_key_rate_from_api()
            assert rate is None

    def test_fetch_rate_not_found(self):
        """Ключевая ставка не найдена на странице."""
        mock_response = MagicMock()
        mock_response.text = '<html><body>Нет информации о ставке</body></html>'
        mock_response.raise_for_status = MagicMock()

        with patch('requests.get', return_value=mock_response):
            rate = _fetch_key_rate_from_api()
            assert rate is None

    def test_fetch_invalid_rate_format(self):
        """Некорректный формат ставки."""
        mock_response = MagicMock()
        mock_response.text = '<html><body>Ключевая ставка: invalid</body></html>'
        mock_response.raise_for_status = MagicMock()

        with patch('requests.get', return_value=mock_response):
            rate = _fetch_key_rate_from_api()
            assert rate is None


@pytest.mark.unit
class TestGetKeyRate:
    """Тесты получения ключевой ставки с кэшированием."""

    def test_get_key_rate_from_api(self):
        """Получение ставки с API при пустом кэше."""
        with patch('bot.handlers.game.cbr_service._is_cache_valid', return_value=False), \
             patch('bot.handlers.game.cbr_service._fetch_key_rate_from_api', return_value=21.0):

            rate = get_key_rate()
            assert rate == 21.0

    def test_get_key_rate_from_cache(self):
        """Получение ставки из кэша."""
        with patch('bot.handlers.game.cbr_service._is_cache_valid', return_value=True), \
             patch('bot.handlers.game.cbr_service._cached_rate', 21.0):

            # Устанавливаем кэш
            import bot.handlers.game.cbr_service as cbr_module
            cbr_module._cached_rate = 21.0
            cbr_module._cache_timestamp = datetime.utcnow()

            rate = get_key_rate()
            assert rate == 21.0

    def test_get_key_rate_fallback_with_stale_cache(self):
        """Fallback на устаревший кэш при ошибке API."""
        import bot.handlers.game.cbr_service as cbr_module
        cbr_module._cached_rate = 18.0
        cbr_module._cache_timestamp = datetime.utcnow() - timedelta(hours=2)

        with patch('bot.handlers.game.cbr_service._is_cache_valid', return_value=False), \
             patch('bot.handlers.game.cbr_service._fetch_key_rate_from_api', return_value=None):

            rate = get_key_rate()
            assert rate == 18.0

    def test_get_key_rate_fallback_no_cache(self):
        """Fallback на фиксированное значение при отсутствии кэша и ошибке API."""
        import bot.handlers.game.cbr_service as cbr_module
        cbr_module._cached_rate = None
        cbr_module._cache_timestamp = None

        with patch('bot.handlers.game.cbr_service._is_cache_valid', return_value=False), \
             patch('bot.handlers.game.cbr_service._fetch_key_rate_from_api', return_value=None):

            rate = get_key_rate()
            assert rate == FALLBACK_COMMISSION_PERCENT


@pytest.mark.unit
class TestCalculateCommissionPercent:
    """Тесты получения процента комиссии."""

    def test_calculate_commission_percent(self):
        """Процент комиссии равен ключевой ставке."""
        with patch('bot.handlers.game.cbr_service.get_key_rate', return_value=21.0):
            percent = calculate_commission_percent()
            assert percent == 21.0


@pytest.mark.unit
class TestCalculateCommissionAmount:
    """Тесты расчёта суммы комиссии."""

    def test_calculate_commission_21_percent_price_10(self):
        """Комиссия 21% от 10 = 2."""
        with patch('bot.handlers.game.cbr_service.calculate_commission_percent', return_value=21.0):
            commission = calculate_commission_amount(10)
            assert commission == 2  # 10 * 0.21 = 2.1 -> 2

    def test_calculate_commission_21_percent_price_8(self):
        """Комиссия 21% от 8 = 1 (минимум)."""
        with patch('bot.handlers.game.cbr_service.calculate_commission_percent', return_value=21.0):
            commission = calculate_commission_amount(8)
            assert commission == 1  # 8 * 0.21 = 1.68 -> 1

    def test_calculate_commission_21_percent_price_3(self):
        """Комиссия 21% от 3 = 1 (минимум)."""
        with patch('bot.handlers.game.cbr_service.calculate_commission_percent', return_value=21.0):
            commission = calculate_commission_amount(3)
            assert commission == 1  # 3 * 0.21 = 0.63 -> 0, но минимум 1

    def test_calculate_commission_minimum(self):
        """Минимальная комиссия 1 койн."""
        with patch('bot.handlers.game.cbr_service.calculate_commission_percent', return_value=21.0):
            commission = calculate_commission_amount(1)
            assert commission == MIN_COMMISSION

    def test_calculate_commission_10_percent_fallback(self):
        """Комиссия 10% (fallback) от 50 = 5."""
        with patch('bot.handlers.game.cbr_service.calculate_commission_percent', return_value=10.0):
            commission = calculate_commission_amount(50)
            assert commission == 5  # 50 * 0.10 = 5

    def test_calculate_commission_large_amount(self):
        """Комиссия для большой суммы."""
        with patch('bot.handlers.game.cbr_service.calculate_commission_percent', return_value=21.0):
            commission = calculate_commission_amount(1000)
            assert commission == 210  # 1000 * 0.21 = 210

    def test_calculate_commission_invalid_price(self):
        """Ошибка при некорректной цене."""
        with pytest.raises(ValueError, match="Price must be positive"):
            calculate_commission_amount(0)

        with pytest.raises(ValueError, match="Price must be positive"):
            calculate_commission_amount(-10)


@pytest.mark.unit
class TestCacheValidation:
    """Тесты валидации кэша."""

    def test_cache_valid_fresh(self):
        """Кэш валиден (свежий)."""
        import bot.handlers.game.cbr_service as cbr_module
        cbr_module._cached_rate = 21.0
        cbr_module._cache_timestamp = datetime.utcnow()

        assert _is_cache_valid() is True

    def test_cache_invalid_old(self):
        """Кэш невалиден (устарел)."""
        import bot.handlers.game.cbr_service as cbr_module
        cbr_module._cached_rate = 21.0
        cbr_module._cache_timestamp = datetime.utcnow() - timedelta(hours=2)

        assert _is_cache_valid() is False

    def test_cache_invalid_empty(self):
        """Кэш невалиден (пустой)."""
        import bot.handlers.game.cbr_service as cbr_module
        cbr_module._cached_rate = None
        cbr_module._cache_timestamp = None

        assert _is_cache_valid() is False
