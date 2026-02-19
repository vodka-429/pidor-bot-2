"""Integration tests for configuration system."""
import json
import os
import pytest
import tempfile
from datetime import date
from unittest.mock import MagicMock, AsyncMock, patch

from bot.handlers.game.config import (
    GameConstants,
    ChatConfig,
    GlobalConfig,
    get_config,
    get_enabled_chats,
    get_test_chat_id,
    is_test_chat,
)
from bot.handlers.game.text_static import (
    get_shop_menu,
    get_immunity_messages,
    get_double_chance_messages,
    get_prediction_messages,
    get_reroll_messages,
    get_transfer_messages,
    get_rules_message,
)


@pytest.fixture
def custom_config_file():
    """Create a config file with custom prices for testing."""
    config_data = {
        "enabled_chats": [-1001392307997, -4608252738],
        "test_chat_id": -4608252738,
        "defaults": {
            "immunity_price": 15,
            "double_chance_price": 12,
            "prediction_price": 5,
            "reroll_price": 20,
            "coins_per_win": 6,
            "prediction_reward": 40,
        },
        "chat_overrides": {
            "-4608252738": {
                "immunity_price": 8,
                "double_chance_price": 6,
                "prediction_price": 3,
                "reroll_price": 10,
                "coins_per_win": 3,
                "prediction_reward": 25,
                "max_missed_days_for_final_voting": 100,
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def feature_flags_config_file():
    """Create a config file with disabled features for testing."""
    config_data = {
        "enabled_chats": [-1001392307997, -4608252738],
        "test_chat_id": -4608252738,
        "defaults": {},
        "chat_overrides": {
            "-1001392307997": {
                "reroll_enabled": False,
                "transfer_enabled": False,
                "prediction_enabled": False,
            },
            "-4608252738": {
                "immunity_enabled": False,
                "double_chance_enabled": False,
                "give_coins_enabled": False,
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    yield temp_path

    if os.path.exists(temp_path):
        os.unlink(temp_path)


@pytest.fixture
def reset_global_config():
    """Reset global config before and after each test."""
    import bot.handlers.game.config as config_module
    original_config = config_module._global_config
    config_module._global_config = None
    yield
    config_module._global_config = original_config


@pytest.mark.integration
def test_full_cycle_with_custom_prices(custom_config_file, reset_global_config):
    """Test full cycle: load config → get prices → verify in messages."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': custom_config_file}):
        # Get config for test chat with overrides
        config = get_config(-4608252738)

        # Verify custom prices are loaded
        assert config.constants.immunity_price == 8
        assert config.constants.double_chance_price == 6
        assert config.constants.prediction_price == 3
        assert config.constants.reroll_price == 10
        assert config.constants.coins_per_win == 3
        assert config.constants.prediction_reward == 25

        # Verify prices are reflected in shop menu
        shop_menu = get_shop_menu(config)
        assert "8" in shop_menu  # immunity_price
        assert "6" in shop_menu  # double_chance_price
        assert "3" in shop_menu  # prediction_price
        assert "25" in shop_menu  # prediction_reward

        # Verify prices in specific messages
        immunity_msgs = get_immunity_messages(config)
        assert "8" in immunity_msgs['purchase_success']

        double_chance_msgs = get_double_chance_messages(config)
        assert "6" in double_chance_msgs['purchase_success_self']

        prediction_msgs = get_prediction_messages(config)
        assert "3" in prediction_msgs['purchase_success']
        assert "25" in prediction_msgs['result_correct']

        reroll_msgs = get_reroll_messages(config)
        assert "10" in reroll_msgs['button_text']

        # Verify prices in rules message
        rules = get_rules_message(config)
        assert "8" in rules  # immunity_price
        assert "6" in rules  # double_chance_price
        assert "3" in rules  # prediction_price
        assert "10" in rules  # reroll_price
        assert "25" in rules  # prediction_reward


@pytest.mark.integration
def test_default_chat_uses_default_prices(custom_config_file, reset_global_config):
    """Test that chat without overrides uses default prices."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': custom_config_file}):
        # Get config for chat without overrides
        config = get_config(-1001392307997)

        # Verify default prices are used
        assert config.constants.immunity_price == 15
        assert config.constants.double_chance_price == 12
        assert config.constants.prediction_price == 5
        assert config.constants.reroll_price == 20
        assert config.constants.coins_per_win == 6
        assert config.constants.prediction_reward == 40

        # Verify prices in shop menu
        shop_menu = get_shop_menu(config)
        assert "15" in shop_menu  # immunity_price
        assert "12" in shop_menu  # double_chance_price
        assert "5" in shop_menu  # prediction_price
        assert "40" in shop_menu  # prediction_reward


@pytest.mark.integration
def test_shop_with_custom_prices(custom_config_file, reset_global_config, mock_db_session, mock_game, sample_players, mocker):
    """Test shop operations work correctly with custom prices."""
    from bot.handlers.game.shop_service import buy_immunity, buy_double_chance, create_prediction
    from bot.app.models import GamePlayerEffect

    with patch.dict(os.environ, {'GAME_CONFIG_PATH': custom_config_file}):
        game_id = mock_game.id
        user_id = sample_players[0].id
        year = 2024
        current_date = date(2024, 6, 15)
        day = 167

        # Mock get_config_by_game_id to return test chat config
        mock_config = get_config(-4608252738)
        mocker.patch('bot.handlers.game.shop_service.get_config_by_game_id', return_value=mock_config)

        # Mock player effects
        mock_effect = GamePlayerEffect(game_id=game_id, user_id=user_id)
        mocker.patch('bot.handlers.game.shop_service.get_or_create_player_effects', return_value=mock_effect)

        # Mock can_afford to return True
        mocker.patch('bot.handlers.game.shop_service.can_afford', return_value=True)

        # Mock spend_coins
        mock_spend = mocker.patch('bot.handlers.game.shop_service.spend_coins')

        # Mock get_or_create_chat_bank
        mock_bank = MagicMock()
        mock_bank.balance = 0
        mocker.patch('bot.handlers.game.transfer_service.get_or_create_chat_bank', return_value=mock_bank)

        # Test immunity purchase with custom price (8 coins)
        success, message, commission = buy_immunity(mock_db_session, game_id, user_id, year, current_date)
        assert success is True
        mock_spend.assert_called_with(mock_db_session, game_id, user_id, 8, year, "shop_immunity", auto_commit=False)

        # Reset mock
        mock_spend.reset_mock()

        # Mock exec for double chance
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        # Test double chance purchase with custom price (6 coins)
        success, message, commission = buy_double_chance(mock_db_session, game_id, user_id, user_id, year, current_date)
        assert success is True
        # Reason includes target_id
        mock_spend.assert_called_with(mock_db_session, game_id, user_id, 6, year, f"shop_double_chance_for_{user_id}", auto_commit=False)

        # Reset mock
        mock_spend.reset_mock()

        # Test prediction purchase with custom price (3 coins)
        success, message, commission = create_prediction(mock_db_session, game_id, user_id, [sample_players[1].id], year, day)
        assert success is True
        mock_spend.assert_called_with(mock_db_session, game_id, user_id, 3, year, "shop_prediction", auto_commit=False)


@pytest.mark.integration
def test_reroll_disabled_raises_error(feature_flags_config_file, reset_global_config, mock_db_session, mock_game, sample_players, mocker):
    """Test that attempting to use reroll when disabled raises an error."""
    from bot.handlers.game.reroll_service import execute_reroll

    with patch.dict(os.environ, {'GAME_CONFIG_PATH': feature_flags_config_file}):
        game_id = mock_game.id
        year = 2024
        day = 100
        initiator_id = sample_players[0].id
        current_date = date(2024, 4, 10)

        # Mock get_config_by_game_id to return chat with reroll disabled
        mock_config = get_config(-1001392307997)
        assert mock_config.constants.reroll_enabled is False
        mocker.patch('bot.handlers.game.reroll_service.get_config_by_game_id', return_value=mock_config)

        # Mock GameResult
        mock_game_result = MagicMock()
        mock_game_result.winner_id = sample_players[1].id
        mock_game_result.reroll_available = True

        mock_result = MagicMock()
        mock_result.first.return_value = mock_game_result
        mock_db_session.exec.return_value = mock_result

        # Attempt to execute reroll should raise ValueError
        with pytest.raises(ValueError, match="Reroll is disabled"):
            execute_reroll(mock_db_session, game_id, year, day, initiator_id, sample_players, current_date)


@pytest.mark.integration
def test_transfer_disabled_raises_error(feature_flags_config_file, reset_global_config, mock_db_session, mock_game, sample_players, mocker):
    """Test that attempting to use transfer when disabled raises an error."""
    from bot.handlers.game.transfer_service import execute_transfer

    with patch.dict(os.environ, {'GAME_CONFIG_PATH': feature_flags_config_file}):
        game_id = mock_game.id
        from_user_id = sample_players[0].id
        to_user_id = sample_players[1].id
        amount = 5
        year = 2024

        # Mock get_config_by_game_id to return chat with transfer disabled
        mock_config = get_config(-1001392307997)
        assert mock_config.constants.transfer_enabled is False
        mocker.patch('bot.handlers.game.transfer_service.get_config_by_game_id', return_value=mock_config)

        # Attempt to execute transfer should raise ValueError
        with pytest.raises(ValueError, match="Transfer is disabled"):
            execute_transfer(mock_db_session, game_id, from_user_id, to_user_id, amount, year, day=100)


@pytest.mark.integration
def test_disabled_features_not_in_shop_menu(feature_flags_config_file, reset_global_config):
    """Test that disabled features are not shown in shop menu."""
    from bot.handlers.game.shop_helpers import create_shop_keyboard

    with patch.dict(os.environ, {'GAME_CONFIG_PATH': feature_flags_config_file}):
        # Get config for chat with some features disabled
        config = get_config(-4608252738)
        assert config.constants.immunity_enabled is False
        assert config.constants.double_chance_enabled is False
        assert config.constants.give_coins_enabled is False

        # Create shop keyboard
        keyboard = create_shop_keyboard(owner_user_id=123, chat_id=-4608252738)

        # Convert keyboard to list of button texts
        button_texts = []
        for row in keyboard.inline_keyboard:
            for button in row:
                button_texts.append(button.text)

        # Verify disabled features are not in keyboard
        assert not any("🛡️" in text for text in button_texts), "Immunity should not be in keyboard"
        assert not any("🎲" in text for text in button_texts), "Double chance should not be in keyboard"

        # Verify enabled features are in keyboard
        assert any("🔮" in text for text in button_texts), "Prediction should be in keyboard"
        assert any("💸" in text for text in button_texts), "Transfer should be in keyboard"
        assert any("🏦" in text for text in button_texts), "Bank should be in keyboard"


@pytest.mark.integration
def test_disabled_features_buttons_not_created(feature_flags_config_file, reset_global_config):
    """Test that buttons for disabled features are not created."""
    from bot.handlers.game.shop_helpers import create_shop_keyboard

    with patch.dict(os.environ, {'GAME_CONFIG_PATH': feature_flags_config_file}):
        # Test chat with immunity, double_chance, give_coins disabled
        config = get_config(-4608252738)

        keyboard = create_shop_keyboard(owner_user_id=123, chat_id=-4608252738)

        # Count total buttons
        total_buttons = sum(len(row) for row in keyboard.inline_keyboard)

        # With 3 features disabled (immunity, double_chance, give_coins), we should have fewer buttons
        # All features: immunity, double_chance, prediction, achievements, transfer, bank = 6 items
        # Disabled: immunity, double_chance, give_coins (give_coins не в магазине) = 2 disabled
        # Expected: 4 buttons (prediction, achievements, transfer, bank)
        assert total_buttons == 4


@pytest.mark.integration
def test_all_features_disabled_shop_menu(reset_global_config):
    """Test shop menu when all features are disabled."""
    from bot.handlers.game.shop_helpers import create_shop_keyboard

    config_data = {
        "enabled_chats": [123],
        "test_chat_id": None,
        "defaults": {},
        "chat_overrides": {
            "123": {
                "reroll_enabled": False,
                "transfer_enabled": False,
                "prediction_enabled": False,
                "immunity_enabled": False,
                "double_chance_enabled": False,
                "give_coins_enabled": False,
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_path}):
            config = get_config(123)

            # Verify all features are disabled
            assert config.constants.reroll_enabled is False
            assert config.constants.transfer_enabled is False
            assert config.constants.prediction_enabled is False
            assert config.constants.immunity_enabled is False
            assert config.constants.double_chance_enabled is False
            assert config.constants.give_coins_enabled is False

            # Create shop keyboard
            keyboard = create_shop_keyboard(owner_user_id=123, chat_id=123)

            # Should have achievements and bank buttons (both are always available)
            total_buttons = sum(len(row) for row in keyboard.inline_keyboard)
            assert total_buttons == 2

            # Verify buttons are achievements and bank
            button_texts = [row[0].text for row in keyboard.inline_keyboard]
            assert any("🎖️" in text or "достижения" in text.lower() for text in button_texts)
            assert any("🏦" in text or "банк" in text.lower() for text in button_texts)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


@pytest.mark.integration
def test_transfer_button_not_shown_when_disabled(feature_flags_config_file, reset_global_config):
    """Test that transfer button is not shown when transfer is disabled."""
    from bot.handlers.game.shop_helpers import create_transfer_amount_keyboard

    with patch.dict(os.environ, {'GAME_CONFIG_PATH': feature_flags_config_file}):
        # Get config for chat with transfer disabled
        config = get_config(-1001392307997)
        assert config.constants.transfer_enabled is False

        # Create transfer keyboard - should return keyboard with only back button when disabled
        keyboard = create_transfer_amount_keyboard(balance=100, receiver_id=123, owner_user_id=456, chat_id=-1001392307997)

        # Should have only back button when transfer is disabled
        total_buttons = sum(len(row) for row in keyboard.inline_keyboard)
        assert total_buttons == 1
        assert "Назад" in keyboard.inline_keyboard[0][0].text or "Back" in keyboard.inline_keyboard[0][0].text


@pytest.mark.integration
def test_config_affects_game_logic(custom_config_file, reset_global_config):
    """Test that config changes affect actual game logic - verify constants are loaded correctly."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': custom_config_file}):
        # Get config for test chat
        mock_config = get_config(-4608252738)

        # Verify custom values are loaded correctly
        assert mock_config.constants.coins_per_win == 3  # Custom value, not default 4
        assert mock_config.constants.immunity_price == 8  # Custom value, not default 10
        assert mock_config.constants.prediction_reward == 25  # Custom value, not default 30

        # Get config for default chat
        default_config = get_config(-1001392307997)

        # Verify default values are used
        assert default_config.constants.coins_per_win == 6  # From defaults in config
        assert default_config.constants.immunity_price == 15  # From defaults in config


@pytest.mark.integration
def test_message_prices_match_config(custom_config_file, reset_global_config):
    """Test that all message prices match the configuration."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': custom_config_file}):
        config = get_config(-4608252738)

        # Get all message generators
        shop_menu = get_shop_menu(config)
        immunity_msgs = get_immunity_messages(config)
        double_chance_msgs = get_double_chance_messages(config)
        prediction_msgs = get_prediction_messages(config)
        reroll_msgs = get_reroll_messages(config)
        transfer_msgs = get_transfer_messages(config)
        rules = get_rules_message(config)

        # Verify immunity price (8) appears in relevant messages
        assert str(config.constants.immunity_price) in shop_menu
        assert str(config.constants.immunity_price) in immunity_msgs['purchase_success']
        assert str(config.constants.immunity_price) in rules

        # Verify double chance price (6) appears in relevant messages
        assert str(config.constants.double_chance_price) in shop_menu
        assert str(config.constants.double_chance_price) in double_chance_msgs['purchase_success_self']
        assert str(config.constants.double_chance_price) in rules

        # Verify prediction price (3) and reward (25) appear in relevant messages
        assert str(config.constants.prediction_price) in shop_menu
        assert str(config.constants.prediction_price) in prediction_msgs['purchase_success']
        assert str(config.constants.prediction_reward) in shop_menu
        assert str(config.constants.prediction_reward) in prediction_msgs['result_correct']
        assert str(config.constants.prediction_price) in rules
        assert str(config.constants.prediction_reward) in rules

        # Verify reroll price (10) appears in relevant messages
        assert str(config.constants.reroll_price) in reroll_msgs['button_text']
        assert str(config.constants.reroll_price) in rules

        # Verify transfer min amount (2) appears in relevant messages
        assert str(config.constants.transfer_min_amount) in transfer_msgs['error_min_amount']


@pytest.mark.integration
def test_feature_flags_prevent_operations(feature_flags_config_file, reset_global_config, mock_db_session, mock_game, sample_players, mocker):
    """Test that feature flags prevent operations from being executed."""
    from bot.handlers.game.shop_service import buy_immunity, buy_double_chance, create_prediction

    with patch.dict(os.environ, {'GAME_CONFIG_PATH': feature_flags_config_file}):
        game_id = mock_game.id
        user_id = sample_players[0].id
        year = 2024
        current_date = date(2024, 6, 15)
        day = 167

        # Mock get_config_by_game_id to return test chat with features disabled
        mock_config = get_config(-4608252738)
        assert mock_config.constants.immunity_enabled is False
        assert mock_config.constants.double_chance_enabled is False
        mocker.patch('bot.handlers.game.shop_service.get_config_by_game_id', return_value=mock_config)

        # Mock player effects for immunity
        from bot.app.models import GamePlayerEffect
        mock_effect = GamePlayerEffect(game_id=game_id, user_id=user_id)
        mocker.patch('bot.handlers.game.shop_service.get_or_create_player_effects', return_value=mock_effect)
        mocker.patch('bot.handlers.game.shop_service.can_afford', return_value=True)
        mocker.patch('bot.handlers.game.transfer_service.get_or_create_chat_bank', return_value=MagicMock(balance=0))

        # Attempt to buy immunity should return failure with "feature_disabled" message
        success, message, commission = buy_immunity(mock_db_session, game_id, user_id, year, current_date)
        assert success is False
        assert message == "feature_disabled"
        assert commission == 0

        # Mock exec for double chance
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        # Attempt to buy double chance should return failure with "feature_disabled" message
        success, message, commission = buy_double_chance(mock_db_session, game_id, user_id, user_id, year, current_date)
        assert success is False
        assert message == "feature_disabled"
        assert commission == 0

        # Test chat with prediction disabled
        mock_config2 = get_config(-1001392307997)
        assert mock_config2.constants.prediction_enabled is False
        mocker.patch('bot.handlers.game.shop_service.get_config_by_game_id', return_value=mock_config2)

        # Attempt to create prediction should return failure with "feature_disabled" message
        success, message, commission = create_prediction(mock_db_session, game_id, user_id, [sample_players[1].id], year, day)
        assert success is False
        assert message == "feature_disabled"
        assert commission == 0
