"""Tests for give coins service."""
import pytest
from unittest.mock import MagicMock, patch

from bot.app.models import GiveCoinsClick
from bot.handlers.game.give_coins_service import (
    has_claimed_today,
    claim_coins,
)


@pytest.mark.unit
class TestHasClaimedToday:
    """Тесты проверки получения койнов сегодня."""

    def test_has_claimed_today_false_when_no_clicks(self, mock_db_session):
        """Койны не получены сегодня - нет записей."""
        # Mock no click found
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        assert not has_claimed_today(mock_db_session, 1, 1, 2026, 22)

    def test_has_claimed_today_true_when_clicked(self, mock_db_session):
        """Койны уже получены сегодня."""
        # Mock click found
        mock_click = MagicMock()
        mock_result = MagicMock()
        mock_result.first.return_value = mock_click
        mock_db_session.exec.return_value = mock_result

        assert has_claimed_today(mock_db_session, 1, 1, 2026, 22)

    def test_has_claimed_today_different_day(self, mock_db_session):
        """Койны получены в другой день."""
        # Mock no click found for today
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        assert not has_claimed_today(mock_db_session, 1, 1, 2026, 22)

    def test_has_claimed_today_different_user(self, mock_db_session):
        """Другой пользователь получил койны."""
        # Mock no click found for this user
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        assert not has_claimed_today(mock_db_session, 1, 2, 2026, 22)


@pytest.mark.unit
class TestClaimCoins:
    """Тесты получения койнов."""

    def test_claim_coins_success_regular_player(self, mock_db_session, mock_game):
        """Успешное получение койнов обычным игроком."""
        # Mock no previous click
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.give_coins_service.add_coins') as mock_add, \
             patch('bot.handlers.game.give_coins_service.get_config_by_game_id') as mock_config:
            # Mock config with default values
            mock_cfg = MagicMock()
            mock_cfg.constants.give_coins_enabled = True
            mock_cfg.constants.give_coins_amount = 1
            mock_cfg.constants.give_coins_winner_amount = 2
            mock_config.return_value = mock_cfg

            success, amount = claim_coins(
                mock_db_session, 1, 1, 2026, 22, is_winner=False
            )

        assert success is True
        assert amount == 1

        # Verify add_coins called
        mock_add.assert_called_once_with(
            mock_db_session, 1, 1, 1, 2026,
            "give_coins_button", auto_commit=False
        )

        # Verify GiveCoinsClick created
        mock_db_session.add.assert_called_once()
        added_click = mock_db_session.add.call_args[0][0]
        assert isinstance(added_click, GiveCoinsClick)
        assert added_click.game_id == 1
        assert added_click.user_id == 1
        assert added_click.year == 2026
        assert added_click.day == 22
        assert added_click.is_winner is False
        assert added_click.amount == 1

        # Verify commit called
        mock_db_session.commit.assert_called_once()

    def test_claim_coins_success_winner(self, mock_db_session, mock_game):
        """Успешное получение койнов пидором дня."""
        # Mock no previous click
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.give_coins_service.add_coins') as mock_add, \
             patch('bot.handlers.game.give_coins_service.get_config_by_game_id') as mock_config:
            # Mock config with default values
            mock_cfg = MagicMock()
            mock_cfg.constants.give_coins_enabled = True
            mock_cfg.constants.give_coins_amount = 1
            mock_cfg.constants.give_coins_winner_amount = 2
            mock_config.return_value = mock_cfg

            success, amount = claim_coins(
                mock_db_session, 1, 2, 2026, 22, is_winner=True
            )

        assert success is True
        assert amount == 2

        # Verify add_coins called with winner amount
        mock_add.assert_called_once_with(
            mock_db_session, 1, 2, 2, 2026,
            "give_coins_button", auto_commit=False
        )

        # Verify GiveCoinsClick created with winner flag
        added_click = mock_db_session.add.call_args[0][0]
        assert added_click.is_winner is True
        assert added_click.amount == 2

    def test_claim_coins_already_claimed(self, mock_db_session, mock_game):
        """Койны уже получены сегодня."""
        # Mock existing click
        mock_click = MagicMock()
        mock_result = MagicMock()
        mock_result.first.return_value = mock_click
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.give_coins_service.add_coins') as mock_add, \
             patch('bot.handlers.game.give_coins_service.get_config_by_game_id') as mock_config:
            # Mock config with default values
            mock_cfg = MagicMock()
            mock_cfg.constants.give_coins_enabled = True
            mock_cfg.constants.give_coins_amount = 1
            mock_cfg.constants.give_coins_winner_amount = 2
            mock_config.return_value = mock_cfg

            success, amount = claim_coins(
                mock_db_session, 1, 1, 2026, 22, is_winner=False
            )

        assert success is False
        assert amount == 0

        # Verify add_coins NOT called
        mock_add.assert_not_called()

        # Verify no new click created
        mock_db_session.add.assert_not_called()

        # Verify no commit
        mock_db_session.commit.assert_not_called()

    def test_claim_coins_different_games(self, mock_db_session, mock_game):
        """Получение койнов в разных играх."""
        # Mock no click in game 2
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.give_coins_service.add_coins') as mock_add, \
             patch('bot.handlers.game.give_coins_service.get_config_by_game_id') as mock_config:
            # Mock config with default values
            mock_cfg = MagicMock()
            mock_cfg.constants.give_coins_enabled = True
            mock_cfg.constants.give_coins_amount = 1
            mock_cfg.constants.give_coins_winner_amount = 2
            mock_config.return_value = mock_cfg

            success, amount = claim_coins(
                mock_db_session, 2, 1, 2026, 22, is_winner=False
            )

        assert success is True
        assert amount == 1

        # Verify add_coins called for game 2
        mock_add.assert_called_once_with(
            mock_db_session, 2, 1, 1, 2026,
            "give_coins_button", auto_commit=False
        )

    def test_claim_coins_different_days(self, mock_db_session, mock_game):
        """Получение койнов в разные дни."""
        # Mock no click for day 23
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.give_coins_service.add_coins') as mock_add, \
             patch('bot.handlers.game.give_coins_service.get_config_by_game_id') as mock_config:
            # Mock config with default values
            mock_cfg = MagicMock()
            mock_cfg.constants.give_coins_enabled = True
            mock_cfg.constants.give_coins_amount = 1
            mock_cfg.constants.give_coins_winner_amount = 2
            mock_config.return_value = mock_cfg

            success, amount = claim_coins(
                mock_db_session, 1, 1, 2026, 23, is_winner=False
            )

        assert success is True
        assert amount == 1

        # Verify GiveCoinsClick created for day 23
        added_click = mock_db_session.add.call_args[0][0]
        assert added_click.day == 23

    def test_claim_coins_winner_amount_is_double(self):
        """Пидор дня получает в 2 раза больше (по умолчанию)."""
        # Проверяем значения по умолчанию из конфигурации
        from bot.handlers.game.config import GameConstants
        defaults = GameConstants()
        assert defaults.give_coins_winner_amount == defaults.give_coins_amount * 2

    def test_claim_coins_multiple_users_same_day(self, mock_db_session, mock_game):
        """Несколько пользователей могут получить койны в один день."""
        # Mock no click for user 3
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        with patch('bot.handlers.game.give_coins_service.add_coins') as mock_add, \
             patch('bot.handlers.game.give_coins_service.get_config_by_game_id') as mock_config:
            # Mock config with default values
            mock_cfg = MagicMock()
            mock_cfg.constants.give_coins_enabled = True
            mock_cfg.constants.give_coins_amount = 1
            mock_cfg.constants.give_coins_winner_amount = 2
            mock_config.return_value = mock_cfg

            success, amount = claim_coins(
                mock_db_session, 1, 3, 2026, 22, is_winner=False
            )

        assert success is True
        assert amount == 1

        # Verify GiveCoinsClick created for user 3
        added_click = mock_db_session.add.call_args[0][0]
        assert added_click.user_id == 3

    def test_claim_coins_disabled_feature(self, mock_db_session, mock_game):
        """Попытка получить койны при отключенной функции."""
        with patch('bot.handlers.game.give_coins_service.get_config_by_game_id') as mock_config:
            # Mock config with disabled give_coins
            mock_cfg = MagicMock()
            mock_cfg.constants.give_coins_enabled = False
            mock_config.return_value = mock_cfg

            with pytest.raises(ValueError, match="Give coins feature is disabled"):
                claim_coins(mock_db_session, 1, 1, 2026, 22, is_winner=False)
