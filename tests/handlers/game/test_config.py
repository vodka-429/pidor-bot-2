"""Tests for game configuration module."""
import json
import os
import pytest
import tempfile
from unittest.mock import patch

from bot.handlers.game.config import (
    GameConstants,
    ChatConfig,
    GlobalConfig,
    get_config,
    get_enabled_chats,
    get_test_chat_id,
    is_test_chat,
    _load_global_config,
    _get_global_config
)


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    config_data = {
        "enabled_chats": [-1001392307997, -4608252738, -1002189152002],
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
                "reroll_enabled": False,
                "transfer_enabled": False
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
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


@pytest.mark.unit
def test_game_constants_defaults():
    """Test GameConstants has correct default values."""
    constants = GameConstants()

    # Цены
    assert constants.immunity_price == 10
    assert constants.double_chance_price == 8
    assert constants.prediction_price == 3
    assert constants.reroll_price == 15

    # Награды
    assert constants.coins_per_win == 4
    assert constants.coins_per_command == 1
    assert constants.self_pidor_multiplier == 2
    assert constants.prediction_reward == 30
    assert constants.give_coins_amount == 1
    assert constants.give_coins_winner_amount == 2

    # Лимиты
    assert constants.max_missed_days_for_final_voting == 10
    assert constants.immunity_cooldown_days == 7
    assert constants.transfer_min_amount == 2

    # Таймауты
    assert constants.game_result_time_delay == 2
    assert constants.reroll_timeout_minutes == 5

    # Feature flags
    assert constants.reroll_enabled is True
    assert constants.transfer_enabled is True
    assert constants.prediction_enabled is True
    assert constants.immunity_enabled is True
    assert constants.double_chance_enabled is True
    assert constants.give_coins_enabled is True


@pytest.mark.unit
def test_chat_config_defaults():
    """Test ChatConfig has correct default values."""
    config = ChatConfig(chat_id=123)

    assert config.chat_id == 123
    assert config.enabled is True
    assert config.is_test is False
    assert isinstance(config.constants, GameConstants)


@pytest.mark.unit
def test_global_config_defaults():
    """Test GlobalConfig has correct default values."""
    config = GlobalConfig()

    assert config.enabled_chats == []
    assert config.test_chat_id is None
    assert isinstance(config.defaults, GameConstants)
    assert config.chat_overrides == {}


@pytest.mark.unit
def test_load_global_config_from_file(temp_config_file, reset_global_config):
    """Test loading config from file."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        config = _load_global_config()

        assert config.enabled_chats == [-1001392307997, -4608252738, -1002189152002]
        assert config.test_chat_id == -4608252738
        assert config.defaults.immunity_price == 10
        assert config.defaults.coins_per_win == 4
        assert -4608252738 in config.chat_overrides
        assert config.chat_overrides[-4608252738]['immunity_price'] == 5


@pytest.mark.unit
def test_load_global_config_no_file(reset_global_config):
    """Test loading config when file doesn't exist."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': '/nonexistent/path.json'}):
        config = _load_global_config()

        # Should return empty config
        assert config.enabled_chats == []
        assert config.test_chat_id is None
        assert config.chat_overrides == {}


@pytest.mark.unit
def test_load_global_config_no_path(reset_global_config):
    """Test loading config when path is not set."""
    with patch.dict(os.environ, {}, clear=True):
        config = _load_global_config()

        # Should return empty config
        assert config.enabled_chats == []
        assert config.test_chat_id is None


@pytest.mark.unit
def test_get_config_with_overrides(temp_config_file, reset_global_config):
    """Test get_config applies chat-specific overrides."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        # Test chat with overrides
        config = get_config(-4608252738)

        assert config.chat_id == -4608252738
        assert config.enabled is True
        assert config.is_test is True
        assert config.constants.immunity_price == 5  # Overridden
        assert config.constants.max_missed_days_for_final_voting == 100  # Overridden
        assert config.constants.coins_per_win == 4  # Default


@pytest.mark.unit
def test_get_config_without_overrides(temp_config_file, reset_global_config):
    """Test get_config returns defaults when no overrides."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        # Test chat without overrides
        config = get_config(-1002189152002)

        assert config.chat_id == -1002189152002
        assert config.enabled is True
        assert config.is_test is False
        assert config.constants.immunity_price == 10  # Default
        assert config.constants.max_missed_days_for_final_voting == 10  # Default


@pytest.mark.unit
def test_get_config_feature_flags(temp_config_file, reset_global_config):
    """Test get_config applies feature flag overrides."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        # Test chat with disabled features
        config = get_config(-1001392307997)

        assert config.constants.reroll_enabled is False  # Overridden
        assert config.constants.transfer_enabled is False  # Overridden
        assert config.constants.prediction_enabled is True  # Default


@pytest.mark.unit
def test_get_config_not_enabled_chat(temp_config_file, reset_global_config):
    """Test get_config for chat not in enabled_chats."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        config = get_config(999999)

        assert config.chat_id == 999999
        assert config.enabled is False  # Not in enabled_chats
        assert config.is_test is False


@pytest.mark.unit
def test_get_enabled_chats(temp_config_file, reset_global_config):
    """Test get_enabled_chats returns correct list."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        chats = get_enabled_chats()

        assert chats == [-1001392307997, -4608252738, -1002189152002]


@pytest.mark.unit
def test_get_enabled_chats_empty(reset_global_config):
    """Test get_enabled_chats returns empty list when no config."""
    with patch.dict(os.environ, {}, clear=True):
        chats = get_enabled_chats()

        assert chats == []


@pytest.mark.unit
def test_get_test_chat_id(temp_config_file, reset_global_config):
    """Test get_test_chat_id returns correct ID."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        test_id = get_test_chat_id()

        assert test_id == -4608252738


@pytest.mark.unit
def test_get_test_chat_id_none(reset_global_config):
    """Test get_test_chat_id returns None when not set."""
    with patch.dict(os.environ, {}, clear=True):
        test_id = get_test_chat_id()

        assert test_id is None


@pytest.mark.unit
def test_is_test_chat_true(temp_config_file, reset_global_config):
    """Test is_test_chat returns True for test chat."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        assert is_test_chat(-4608252738) is True


@pytest.mark.unit
def test_is_test_chat_false(temp_config_file, reset_global_config):
    """Test is_test_chat returns False for non-test chat."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        assert is_test_chat(-1001392307997) is False
        assert is_test_chat(999999) is False


@pytest.mark.unit
def test_is_test_chat_no_test_chat_set(reset_global_config):
    """Test is_test_chat returns False when no test chat is set."""
    with patch.dict(os.environ, {}, clear=True):
        assert is_test_chat(-4608252738) is False


@pytest.mark.unit
def test_config_caching(temp_config_file, reset_global_config):
    """Test that global config is cached after first load."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        # First call loads config
        config1 = _get_global_config()

        # Second call should return same instance
        config2 = _get_global_config()

        assert config1 is config2


@pytest.mark.unit
def test_all_features_enabled_by_default(reset_global_config):
    """Test that all feature flags are enabled by default."""
    with patch.dict(os.environ, {}, clear=True):
        config = get_config(123)

        assert config.constants.reroll_enabled is True
        assert config.constants.transfer_enabled is True
        assert config.constants.prediction_enabled is True
        assert config.constants.immunity_enabled is True
        assert config.constants.double_chance_enabled is True
        assert config.constants.give_coins_enabled is True


@pytest.mark.unit
def test_feature_flag_disable_reroll(temp_config_file, reset_global_config):
    """Test disabling reroll feature for specific chat."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        config = get_config(-1001392307997)

        assert config.constants.reroll_enabled is False


@pytest.mark.unit
def test_feature_flag_disable_transfer(temp_config_file, reset_global_config):
    """Test disabling transfer feature for specific chat."""
    with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_config_file}):
        config = get_config(-1001392307997)

        assert config.constants.transfer_enabled is False


@pytest.mark.unit
def test_feature_flag_disable_all_shop_features():
    """Test disabling all shop features for a chat."""
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
                "give_coins_enabled": False
            }
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        import bot.handlers.game.config as config_module
        config_module._global_config = None

        with patch.dict(os.environ, {'GAME_CONFIG_PATH': temp_path}):
            config = get_config(123)

            assert config.constants.reroll_enabled is False
            assert config.constants.transfer_enabled is False
            assert config.constants.prediction_enabled is False
            assert config.constants.immunity_enabled is False
            assert config.constants.double_chance_enabled is False
            assert config.constants.give_coins_enabled is False
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        config_module._global_config = None
