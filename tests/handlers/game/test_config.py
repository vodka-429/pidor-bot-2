"""Tests for game configuration module."""
import json
import os
import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import patch

from bot.handlers.game.config import (
    GameConstants,
    ChatConfig,
    GlobalConfig,
    get_config,
    get_enabled_chats,
    get_test_chat_id,
    is_test_chat,
    _load_config_from_file,
    _load_config_from_env,
    _get_global_config,
)


@pytest.fixture
def reset_global_config():
    """Reset global config before and after each test."""
    import bot.handlers.game.config as config_module
    original_config = config_module._global_config
    config_module._global_config = None
    yield
    config_module._global_config = original_config


@pytest.fixture
def sample_config_data():
    """Sample configuration data for testing."""
    return {
        "enabled_chats": [-1001392307997, -4608252738, -1002189152002, -1003671793100],
        "test_chat_id": -4608252738,
        "defaults": {
            "immunity_price": 10,
            "coins_per_win": 4,
            "reroll_enabled": True,
            "transfer_enabled": True
        },
        "chat_overrides": {
            "-4608252738": {
                "immunity_price": 5,
                "max_missed_days_for_final_voting": 100,
                "reroll_enabled": False
            },
            "-1001392307997": {
                "reroll_enabled": False,
                "transfer_enabled": False
            }
        }
    }


@pytest.fixture
def temp_config_file(sample_config_data):
    """Create a temporary config file for testing."""
    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(sample_config_data, f)
        temp_path = f.name

    yield temp_path

    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


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

    # Feature flags - все включены по умолчанию
    assert constants.reroll_enabled is True
    assert constants.transfer_enabled is True
    assert constants.prediction_enabled is True
    assert constants.immunity_enabled is True
    assert constants.double_chance_enabled is True
    assert constants.give_coins_enabled is True


@pytest.mark.unit
def test_chat_config_defaults():
    """Test ChatConfig has correct default values."""
    config = ChatConfig(chat_id=-123456)

    assert config.chat_id == -123456
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
def test_load_config_from_file(temp_config_file):
    """Test loading configuration from file."""
    config = _load_config_from_file(temp_config_file)

    assert len(config.enabled_chats) == 4
    assert -4608252738 in config.enabled_chats
    assert config.test_chat_id == -4608252738
    assert config.defaults.immunity_price == 10
    assert config.defaults.coins_per_win == 4

    # Check chat overrides
    assert -4608252738 in config.chat_overrides
    assert config.chat_overrides[-4608252738]['immunity_price'] == 5
    assert config.chat_overrides[-4608252738]['max_missed_days_for_final_voting'] == 100


@pytest.mark.unit
def test_load_config_from_file_not_found():
    """Test loading configuration from non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        _load_config_from_file('/nonexistent/path/config.json')


@pytest.mark.unit
def test_load_config_from_file_invalid_json():
    """Test loading configuration from invalid JSON file raises JSONDecodeError."""
    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write("invalid json {")
        temp_path = f.name

    try:
        with pytest.raises(json.JSONDecodeError):
            _load_config_from_file(temp_path)
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.unit
def test_load_config_from_env_no_env_var(reset_global_config):
    """Test loading configuration when GAME_CONFIG env var is not set."""
    with patch.dict(os.environ, {}, clear=True):
        config = _load_config_from_env()

        # Should return default config
        assert isinstance(config, GlobalConfig)
        assert config.enabled_chats == []
        assert config.test_chat_id is None


@pytest.mark.unit
def test_load_config_from_env_with_valid_file(temp_config_file, reset_global_config):
    """Test loading configuration from env var pointing to valid file."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        config = _load_config_from_env()

        assert len(config.enabled_chats) == 4
        assert config.test_chat_id == -4608252738


@pytest.mark.unit
def test_load_config_from_env_with_invalid_file(reset_global_config):
    """Test loading configuration from env var pointing to invalid file."""
    with patch.dict(os.environ, {'GAME_CONFIG': '/nonexistent/config.json'}):
        config = _load_config_from_env()

        # Should fallback to default config
        assert isinstance(config, GlobalConfig)
        assert config.enabled_chats == []


@pytest.mark.unit
def test_get_config_default(reset_global_config):
    """Test get_config returns default configuration."""
    with patch.dict(os.environ, {}, clear=True):
        config = get_config(-123456)

        assert config.chat_id == -123456
        assert config.enabled is False  # Not in enabled_chats
        assert config.is_test is False
        assert config.constants.immunity_price == 10  # Default value


@pytest.mark.unit
def test_get_config_with_overrides(temp_config_file, reset_global_config):
    """Test get_config applies chat-specific overrides."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        # Test chat with overrides
        config = get_config(-4608252738)

        assert config.chat_id == -4608252738
        assert config.enabled is True  # In enabled_chats
        assert config.is_test is True  # Is test chat
        assert config.constants.immunity_price == 5  # Overridden value
        assert config.constants.max_missed_days_for_final_voting == 100  # Overridden value
        assert config.constants.reroll_enabled is False  # Overridden feature flag
        assert config.constants.coins_per_win == 4  # Default value (not overridden)


@pytest.mark.unit
def test_get_config_enabled_chat_without_overrides(temp_config_file, reset_global_config):
    """Test get_config for enabled chat without specific overrides."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        config = get_config(-1002189152002)

        assert config.chat_id == -1002189152002
        assert config.enabled is True  # In enabled_chats
        assert config.is_test is False  # Not test chat
        assert config.constants.immunity_price == 10  # Default value
        assert config.constants.reroll_enabled is True  # Default feature flag


@pytest.mark.unit
def test_get_enabled_chats_default(reset_global_config):
    """Test get_enabled_chats returns empty list by default."""
    with patch.dict(os.environ, {}, clear=True):
        chats = get_enabled_chats()
        assert chats == []


@pytest.mark.unit
def test_get_enabled_chats_from_config(temp_config_file, reset_global_config):
    """Test get_enabled_chats returns list from config."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        chats = get_enabled_chats()

        assert len(chats) == 4
        assert -1001392307997 in chats
        assert -4608252738 in chats
        assert -1002189152002 in chats
        assert -1003671793100 in chats


@pytest.mark.unit
def test_get_test_chat_id_default(reset_global_config):
    """Test get_test_chat_id returns None by default."""
    with patch.dict(os.environ, {}, clear=True):
        test_chat_id = get_test_chat_id()
        assert test_chat_id is None


@pytest.mark.unit
def test_get_test_chat_id_from_config(temp_config_file, reset_global_config):
    """Test get_test_chat_id returns value from config."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        test_chat_id = get_test_chat_id()
        assert test_chat_id == -4608252738


@pytest.mark.unit
def test_is_test_chat_true(temp_config_file, reset_global_config):
    """Test is_test_chat returns True for test chat."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        assert is_test_chat(-4608252738) is True


@pytest.mark.unit
def test_is_test_chat_false(temp_config_file, reset_global_config):
    """Test is_test_chat returns False for non-test chat."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        assert is_test_chat(-1001392307997) is False


@pytest.mark.unit
def test_is_test_chat_no_test_chat_configured(reset_global_config):
    """Test is_test_chat returns False when no test chat is configured."""
    with patch.dict(os.environ, {}, clear=True):
        assert is_test_chat(-123456) is False


# Feature flags tests


@pytest.mark.unit
def test_feature_flag_reroll_disabled(temp_config_file, reset_global_config):
    """Test reroll feature flag can be disabled for specific chat."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        config = get_config(-4608252738)

        assert config.constants.reroll_enabled is False
        # Other features should remain enabled
        assert config.constants.transfer_enabled is True
        assert config.constants.prediction_enabled is True
        assert config.constants.immunity_enabled is True


@pytest.mark.unit
def test_feature_flag_transfer_disabled(temp_config_file, reset_global_config):
    """Test transfer feature flag can be disabled for specific chat."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        config = get_config(-1001392307997)

        assert config.constants.transfer_enabled is False
        assert config.constants.reroll_enabled is False
        # Other features should remain enabled
        assert config.constants.prediction_enabled is True
        assert config.constants.immunity_enabled is True


@pytest.mark.unit
def test_feature_flags_all_disabled():
    """Test all shop features can be disabled for a chat."""
    config_data = {
        "enabled_chats": [-123456],
        "test_chat_id": None,
        "defaults": {},
        "chat_overrides": {
            "-123456": {
                "reroll_enabled": False,
                "transfer_enabled": False,
                "prediction_enabled": False,
                "immunity_enabled": False,
                "double_chance_enabled": False,
                "give_coins_enabled": False
            }
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG': temp_path}):
            import bot.handlers.game.config as config_module
            config_module._global_config = None  # Reset

            config = get_config(-123456)

            # All features should be disabled
            assert config.constants.reroll_enabled is False
            assert config.constants.transfer_enabled is False
            assert config.constants.prediction_enabled is False
            assert config.constants.immunity_enabled is False
            assert config.constants.double_chance_enabled is False
            assert config.constants.give_coins_enabled is False
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.unit
def test_feature_flags_enabled_by_default(reset_global_config):
    """Test all features are enabled by default."""
    with patch.dict(os.environ, {}, clear=True):
        config = get_config(-123456)

        # All features should be enabled by default
        assert config.constants.reroll_enabled is True
        assert config.constants.transfer_enabled is True
        assert config.constants.prediction_enabled is True
        assert config.constants.immunity_enabled is True
        assert config.constants.double_chance_enabled is True
        assert config.constants.give_coins_enabled is True


@pytest.mark.unit
def test_config_caching(temp_config_file, reset_global_config):
    """Test that global config is cached and reused."""
    with patch.dict(os.environ, {'GAME_CONFIG': temp_config_file}):
        # First call should load config
        config1 = _get_global_config()

        # Second call should return cached config
        config2 = _get_global_config()

        # Should be the same object
        assert config1 is config2


@pytest.mark.unit
def test_invalid_chat_id_in_overrides(reset_global_config):
    """Test that invalid chat IDs in overrides are skipped."""
    config_data = {
        "enabled_chats": [-123456],
        "test_chat_id": None,
        "defaults": {},
        "chat_overrides": {
            "invalid_id": {
                "immunity_price": 999
            },
            "-123456": {
                "immunity_price": 5
            }
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        config = _load_config_from_file(temp_path)

        # Invalid chat ID should be skipped
        assert "invalid_id" not in config.chat_overrides
        # Valid chat ID should be present
        assert -123456 in config.chat_overrides
        assert config.chat_overrides[-123456]['immunity_price'] == 5
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.unit
def test_partial_overrides(reset_global_config):
    """Test that partial overrides work correctly (only specified fields are overridden)."""
    config_data = {
        "enabled_chats": [-123456],
        "test_chat_id": None,
        "defaults": {
            "immunity_price": 10,
            "coins_per_win": 4
        },
        "chat_overrides": {
            "-123456": {
                "immunity_price": 5
                # coins_per_win not overridden
            }
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG': temp_path}):
            import bot.handlers.game.config as config_module
            config_module._global_config = None  # Reset

            config = get_config(-123456)

            # Overridden value
            assert config.constants.immunity_price == 5
            # Default value (not overridden)
            assert config.constants.coins_per_win == 4
    finally:
        Path(temp_path).unlink(missing_ok=True)
