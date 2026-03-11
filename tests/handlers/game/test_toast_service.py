"""Tests for toast service."""
import pytest
from unittest.mock import MagicMock, patch

from bot.app.models import ChatBank, Toast
from bot.handlers.game.toast_service import (
    calculate_toast_commission,
    get_or_create_chat_bank,
    execute_toast,
)
from bot.handlers.game.config import GameConstants, ChatConfig


@pytest.mark.unit
class TestCalculateToastCommission:
    """Тесты расчёта комиссии за тост."""

    @patch('bot.handlers.game.toast_service.calculate_commission_amount')
    def test_commission_uses_cbr_service(self, mock_calc):
        """Комиссия рассчитывается через CBR сервис."""
        mock_calc.return_value = 1
        assert calculate_toast_commission(5) == 1
        mock_calc.assert_called_once_with(5)

    @patch('bot.handlers.game.toast_service.calculate_commission_amount')
    def test_commission_minimum_one_coin(self, mock_calc):
        """Минимальная комиссия 1 койн."""
        mock_calc.return_value = 1
        result = calculate_toast_commission(5)
        assert result >= 1


@pytest.mark.unit
class TestGetOrCreateChatBank:
    """Тесты получения/создания банка чата."""

    def test_create_new_bank(self, mock_db_session):
        """Создание нового банка."""
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
        mock_bank = MagicMock()
        mock_bank.id = 1
        mock_bank.game_id = 1
        mock_bank.balance = 50
        mock_result = MagicMock()
        mock_result.first.return_value = mock_bank
        mock_db_session.exec.return_value = mock_result

        bank = get_or_create_chat_bank(mock_db_session, 1)
        assert bank.balance == 50


@pytest.mark.unit
class TestExecuteToast:
    """Тесты выполнения тоста."""

    @patch('bot.handlers.game.toast_service.calculate_commission_amount')
    @patch('bot.handlers.game.toast_service.get_config_by_game_id')
    def test_successful_toast(self, mock_get_config, mock_calc, mock_db_session):
        """Успешный тост."""
        mock_config = ChatConfig(
            chat_id=-1001392307997,
            enabled=True,
            is_test=False,
            constants=GameConstants(toast_enabled=True, toast_price=5)
        )
        mock_get_config.return_value = mock_config
        mock_calc.return_value = 1  # комиссия 1 койн

        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_result = MagicMock()
        mock_result.first.return_value = mock_bank
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.toast_service.spend_coins') as mock_spend, \
             patch('bot.handlers.game.toast_service.add_coins') as mock_add:

            amount_sent, amount_received, commission = execute_toast(
                mock_db_session, 1, 1, 2, 2026
            )

        assert amount_sent == 5
        assert amount_received == 4  # 5 - 1
        assert commission == 1

        mock_spend.assert_called_once_with(
            mock_db_session, 1, 1, 5, 2026, "toast_to_2", auto_commit=False
        )
        mock_add.assert_called_once_with(
            mock_db_session, 1, 2, 4, 2026, "toast_from_1", auto_commit=False
        )
        assert mock_bank.balance == 1

    @patch('bot.handlers.game.toast_service.calculate_commission_amount')
    @patch('bot.handlers.game.toast_service.get_config_by_game_id')
    def test_self_toast_allowed(self, mock_get_config, mock_calc, mock_db_session):
        """Тост самому себе разрешён."""
        mock_config = ChatConfig(
            chat_id=-1001392307997,
            enabled=True,
            is_test=False,
            constants=GameConstants(toast_enabled=True, toast_price=5)
        )
        mock_get_config.return_value = mock_config
        mock_calc.return_value = 1

        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_result = MagicMock()
        mock_result.first.return_value = mock_bank
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.toast_service.spend_coins'), \
             patch('bot.handlers.game.toast_service.add_coins'):

            # sender_id == receiver_id — должно работать без ошибок
            amount_sent, amount_received, commission = execute_toast(
                mock_db_session, 1, 1, 1, 2026
            )

        assert amount_sent == 5
        assert amount_received == 4
        assert commission == 1

    @patch('bot.handlers.game.toast_service.get_config_by_game_id')
    def test_toast_disabled_raises_error(self, mock_get_config, mock_db_session):
        """Нельзя тостить, если функция отключена."""
        mock_config = ChatConfig(
            chat_id=-1001392307997,
            enabled=True,
            is_test=False,
            constants=GameConstants(toast_enabled=False, toast_price=5)
        )
        mock_get_config.return_value = mock_config

        with pytest.raises(ValueError, match="Toast is disabled"):
            execute_toast(mock_db_session, 1, 1, 2, 2026)

    @patch('bot.handlers.game.toast_service.calculate_commission_amount')
    @patch('bot.handlers.game.toast_service.get_config_by_game_id')
    def test_toast_adds_record_to_db(self, mock_get_config, mock_calc, mock_db_session):
        """После тоста создаётся запись Toast в БД."""
        mock_config = ChatConfig(
            chat_id=-1001392307997,
            enabled=True,
            is_test=False,
            constants=GameConstants(toast_enabled=True, toast_price=5)
        )
        mock_get_config.return_value = mock_config
        mock_calc.return_value = 1

        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_result = MagicMock()
        mock_result.first.return_value = mock_bank
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.toast_service.spend_coins'), \
             patch('bot.handlers.game.toast_service.add_coins'):

            execute_toast(mock_db_session, 1, 1, 2, 2026)

        # Проверяем что add был вызван с Toast объектом
        added_objects = [call.args[0] for call in mock_db_session.add.call_args_list]
        toast_objects = [obj for obj in added_objects if isinstance(obj, Toast)]
        assert len(toast_objects) == 1
        assert toast_objects[0].sender_id == 1
        assert toast_objects[0].receiver_id == 2
        assert toast_objects[0].amount == 5
        assert toast_objects[0].commission == 1
        assert toast_objects[0].year == 2026
