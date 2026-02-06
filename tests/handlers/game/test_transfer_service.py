"""Tests for transfer service."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from bot.app.models import ChatBank, CoinTransfer
from bot.handlers.game.transfer_service import (
    calculate_commission,
    has_transferred_today,
    can_transfer,
    get_or_create_chat_bank,
    execute_transfer,
    TRANSFER_MIN_AMOUNT,
)
from bot.handlers.game.cbr_service import MIN_COMMISSION as TRANSFER_MIN_COMMISSION


@pytest.mark.unit
class TestCalculateCommission:
    """Тесты расчёта комиссии."""

    @patch('bot.handlers.game.transfer_service.calculate_commission_amount')
    def test_calculate_commission_uses_cbr_service(self, mock_calc):
        """Комиссия рассчитывается через CBR сервис."""
        mock_calc.return_value = 10
        assert calculate_commission(100) == 10
        mock_calc.assert_called_once_with(100)

    @patch('bot.handlers.game.transfer_service.calculate_commission_amount')
    def test_calculate_commission_minimum(self, mock_calc):
        """Минимальная комиссия 1 койн."""
        mock_calc.return_value = 1
        assert calculate_commission(2) == TRANSFER_MIN_COMMISSION
        mock_calc.assert_called_once_with(2)

    @patch('bot.handlers.game.transfer_service.calculate_commission_amount')
    def test_calculate_commission_rounding(self, mock_calc):
        """Округление комиссии вниз."""
        mock_calc.return_value = 2
        assert calculate_commission(15) == 2
        mock_calc.assert_called_once_with(15)


@pytest.mark.unit
class TestHasTransferredToday:
    """Тесты проверки кулдауна передачи."""

    def test_no_transfer_today(self, mock_db_session):
        """Передач сегодня не было."""
        # Mock no transfer found
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        assert not has_transferred_today(mock_db_session, 1, 1, 2026, 22)

    def test_has_transfer_today(self, mock_db_session):
        """Передача уже была сегодня."""
        # Mock transfer found
        mock_transfer = MagicMock()
        mock_result = MagicMock()
        mock_result.first.return_value = mock_transfer
        mock_db_session.exec.return_value = mock_result

        assert has_transferred_today(mock_db_session, 1, 1, 2026, 22)

    def test_transfer_different_day(self, mock_db_session):
        """Передача была в другой день."""
        # Mock no transfer found for today
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        assert not has_transferred_today(mock_db_session, 1, 1, 2026, 22)


@pytest.mark.unit
class TestCanTransfer:
    """Тесты проверки возможности передачи."""

    def test_can_transfer_ok(self, mock_db_session):
        """Передача доступна."""
        # Mock no transfer found
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        can, error = can_transfer(mock_db_session, 1, 1, 2026, 22)
        assert can is True
        assert error == "ok"

    def test_cannot_transfer_already_today(self, mock_db_session):
        """Передача уже была сегодня."""
        # Mock transfer found
        mock_transfer = MagicMock()
        mock_result = MagicMock()
        mock_result.first.return_value = mock_transfer
        mock_db_session.exec.return_value = mock_result

        can, error = can_transfer(mock_db_session, 1, 1, 2026, 22)
        assert can is False
        assert error == "already_transferred_today"


@pytest.mark.unit
class TestGetOrCreateChatBank:
    """Тесты получения/создания банка чата."""

    def test_create_new_bank(self, mock_db_session):
        """Создание нового банка."""
        # Mock no bank found
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        bank = get_or_create_chat_bank(mock_db_session, 1)
        assert bank is not None
        assert bank.game_id == 1
        assert bank.balance == 0
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    def test_get_existing_bank(self, mock_db_session):
        """Получение существующего банка."""
        # Mock existing bank
        mock_bank = MagicMock()
        mock_bank.id = 1
        mock_bank.game_id = 1
        mock_bank.balance = 100
        mock_result = MagicMock()
        mock_result.first.return_value = mock_bank
        mock_db_session.exec.return_value = mock_result

        bank = get_or_create_chat_bank(mock_db_session, 1)
        assert bank.id == 1
        assert bank.balance == 100


@pytest.mark.unit
class TestExecuteTransfer:
    """Тесты выполнения передачи."""

    @patch('bot.handlers.game.transfer_service.calculate_commission_amount')
    def test_successful_transfer(self, mock_calc, mock_db_session):
        """Успешная передача койнов."""
        # Mock commission calculation (21% от 50 = 10.5 -> 10)
        mock_calc.return_value = 10

        # Mock existing bank
        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_result = MagicMock()
        mock_result.first.return_value = mock_bank
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.transfer_service.spend_coins') as mock_spend, \
             patch('bot.handlers.game.transfer_service.add_coins') as mock_add:

            amount_sent, amount_received, commission = execute_transfer(
                mock_db_session, 1, 1, 2, 50, 2026, 22
            )

        assert amount_sent == 50
        assert amount_received == 40  # 50 - 10
        assert commission == 10

        # Verify spend_coins called
        mock_spend.assert_called_once_with(
            mock_db_session, 1, 1, 50, 2026, "transfer_to_2", auto_commit=False
        )

        # Verify add_coins called
        mock_add.assert_called_once_with(
            mock_db_session, 1, 2, 40, 2026, "transfer_from_1", auto_commit=False
        )

        # Verify bank balance updated
        assert mock_bank.balance == 10

    @patch('bot.handlers.game.transfer_service.calculate_commission_amount')
    def test_transfer_minimum_amount(self, mock_calc, mock_db_session):
        """Передача минимальной суммы."""
        mock_calc.return_value = TRANSFER_MIN_COMMISSION

        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_result = MagicMock()
        mock_result.first.return_value = mock_bank
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.transfer_service.spend_coins'), \
             patch('bot.handlers.game.transfer_service.add_coins'):

            amount_sent, amount_received, commission = execute_transfer(
                mock_db_session, 1, 1, 2, TRANSFER_MIN_AMOUNT, 2026, 22
            )

        assert amount_sent == TRANSFER_MIN_AMOUNT
        assert commission == TRANSFER_MIN_COMMISSION
        assert amount_received == TRANSFER_MIN_AMOUNT - TRANSFER_MIN_COMMISSION

    @patch('bot.handlers.game.transfer_service.calculate_commission_amount')
    def test_transfer_large_amount(self, mock_calc, mock_db_session):
        """Передача большой суммы."""
        # Mock commission (21% от 1000 = 210)
        mock_calc.return_value = 210

        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_result = MagicMock()
        mock_result.first.return_value = mock_bank
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.transfer_service.spend_coins'), \
             patch('bot.handlers.game.transfer_service.add_coins'):

            amount_sent, amount_received, commission = execute_transfer(
                mock_db_session, 1, 1, 2, 1000, 2026, 22
            )

        assert amount_sent == 1000
        assert commission == 210
        assert amount_received == 790
        assert mock_bank.balance == 210

    def test_transfer_to_yourself_raises_error(self, mock_db_session):
        """Нельзя передавать себе."""
        with pytest.raises(ValueError, match="Cannot transfer to yourself"):
            execute_transfer(mock_db_session, 1, 1, 1, 50, 2026, 22)

    def test_transfer_below_minimum_raises_error(self, mock_db_session):
        """Нельзя передавать меньше минимума."""
        with pytest.raises(ValueError, match="Amount must be at least"):
            execute_transfer(mock_db_session, 1, 1, 2, 1, 2026, 22)
