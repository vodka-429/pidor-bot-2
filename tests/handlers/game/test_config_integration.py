"""Интеграционные тесты для конфигурации игры."""
import json
import os
import pytest
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, AsyncMock, patch

from bot.handlers.game.config import get_config, get_enabled_chats
from bot.handlers.game.commands import pidor_cmd
from bot.handlers.game.shop_service import buy_immunity, buy_double_chance, create_prediction
from bot.handlers.game.reroll_service import can_reroll, execute_reroll
from bot.handlers.game.transfer_service import execute_transfer
from bot.handlers.game.give_coins_service import claim_coins
from bot.handlers.game.text_static import get_shop_menu, get_immunity_messages, get_reroll_messages
from bot.app.models import GamePlayerEffect


@pytest.fixture
def custom_config_data():
    """Конфигурация с кастомными ценами для тестового чата."""
    return {
        "enabled_chats": [-1001392307997, -4608252738],
        "test_chat_id": -4608252738,
        "defaults": {
            "immunity_price": 10,
            "coins_per_win": 4,
            "prediction_reward": 30
        },
        "chat_overrides": {
            "-4608252738": {
                "immunity_price": 5,
                "double_chance_price": 4,
                "prediction_price": 2,
                "prediction_reward": 20,
                "reroll_price": 10,
                "coins_per_win": 10
            }
        }
    }


@pytest.fixture
def custom_config_file(custom_config_data):
    """Создать временный файл конфигурации с кастомными ценами."""
    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(custom_config_data, f)
        temp_path = f.name

    yield temp_path

    Path(temp_path).unlink(missing_ok=True)


@pytest.fixture
def reset_config():
    """Сбросить глобальную конфигурацию перед и после теста."""
    import bot.handlers.game.config as config_module
    original_config = config_module._global_config
    config_module._global_config = None
    yield
    config_module._global_config = original_config


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_cycle_with_custom_prices(
    mock_update, mock_context, mock_game, sample_players,
    custom_config_file, reset_config, mocker
):
    """
    Тест полного цикла игры с переопределёнными константами для тестового чата.

    Проверяет:
    - Загрузку конфигурации из файла
    - Применение переопределений для тестового чата
    - Корректную работу игры с кастомными ценами
    """
    # Setup environment
    with patch.dict(os.environ, {'GAME_CONFIG': custom_config_file}):
        # Verify config is loaded correctly
        config = get_config(-4608252738)
        assert config.chat_id == -4608252738
        assert config.is_test is True
        assert config.constants.immunity_price == 5  # Overridden
        assert config.constants.coins_per_win == 10  # Overridden
        assert config.constants.prediction_reward == 20  # Overridden

        # Setup game
        mock_game.chat_id = -4608252738
        mock_game.players = sample_players
        mock_context.game = mock_game

        # Mock queries
        mock_game_query = MagicMock()
        mock_game_query.filter_by.return_value = mock_game_query
        mock_game_query.one_or_none.return_value = mock_game

        mock_missed_query = MagicMock()
        mock_missed_query.filter_by.return_value = mock_missed_query
        mock_missed_query.order_by.return_value = mock_missed_query
        mock_missed_query.first.return_value = None

        mock_result_query = MagicMock()
        mock_result_query.filter_by.return_value = mock_result_query
        mock_result_query.one_or_none.return_value = None

        mock_context.db_session.query.side_effect = [
            mock_game_query, mock_missed_query, mock_result_query
        ]

        # Mock datetime
        mock_dt = MagicMock()
        mock_dt.year = 2024
        mock_dt.month = 6
        mock_dt.day = 15
        mock_dt.date.return_value = date(2024, 6, 15)
        mock_dt.timetuple.return_value.tm_yday = 167
        mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

        # Mock random selection
        winner = sample_players[0]
        mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
            winner,
            "Stage 1", "Stage 2", "Stage 3", "Stage 4: {username}"
        ])

        # Mock other dependencies
        mocker.patch('bot.handlers.game.commands.asyncio.sleep')
        mock_add_coins = mocker.patch('bot.handlers.game.commands.add_coins')
        mocker.patch('bot.handlers.game.commands.get_balance', return_value=100)
        mocker.patch('bot.handlers.game.game_effects_service.get_or_create_player_effects',
                    return_value=GamePlayerEffect(game_id=mock_game.id, user_id=0))

        # Mock predictions
        mock_predictions_result = MagicMock()
        mock_predictions_result.all.return_value = []
        mock_context.db_session.exec.return_value = mock_predictions_result

        mocker.patch('bot.handlers.game.commands.send_result_with_reroll_button', new_callable=AsyncMock)

        # Execute game
        await pidor_cmd(mock_update, mock_context)

        # Verify winner got custom amount of coins
        # В данном случае winner == context.tg_user (self-pidor), поэтому получает 10 * 2 = 20 койнов
        # add_coins вызывается с параметрами: (db_session, game_id, user_id, amount, year, reason, auto_commit)
        winner_coin_calls = [
            call for call in mock_add_coins.call_args_list
            if call[0][2] == winner.id and call[0][5] == 'self_pidor_win'  # user_id и reason
        ]
        assert len(winner_coin_calls) > 0, f"Winner should receive coins for self_pidor_win. Calls: {mock_add_coins.call_args_list}"
        # Проверяем, что сумма = coins_per_win * self_pidor_multiplier = 10 * 2 = 20
        assert winner_coin_calls[0][0][3] == 20, f"Self-pidor should receive 20 coins (10 * 2), got {winner_coin_calls[0][0][3]}"


@pytest.mark.integration
def test_shop_prices_display_correctly(custom_config_file, reset_config):
    """
    Тест корректности отображения цен в сообщениях магазина.

    Проверяет, что цены в меню магазина соответствуют конфигурации.
    """
    with patch.dict(os.environ, {'GAME_CONFIG': custom_config_file}):
        # Get config for test chat
        config = get_config(-4608252738)

        # Generate shop menu
        shop_menu = get_shop_menu(config)

        # Verify custom prices are displayed
        assert "5 койнов" in shop_menu  # Custom immunity price
        assert "4 койнов" in shop_menu  # Custom double chance price
        assert "2 койна" in shop_menu   # Custom prediction price
        assert "20 койнов" in shop_menu  # Custom prediction reward

        # Verify default prices are NOT displayed
        assert "10 койнов" not in shop_menu or shop_menu.count("10 койнов") == 0
        assert "8 койнов" not in shop_menu
        assert "3 койна" not in shop_menu
        assert "30 койнов" not in shop_menu


@pytest.mark.integration
def test_shop_with_custom_prices(mock_db_session, mock_game, sample_players, custom_config_file, reset_config, mocker):
    """
    Тест работы магазина с кастомными ценами.

    Проверяет, что покупки в магазине используют правильные цены из конфигурации.
    """
    with patch.dict(os.environ, {'GAME_CONFIG': custom_config_file}):
        mock_game.chat_id = -4608252738
        chat_id = mock_game.chat_id  # Используем chat_id напрямую
        user_id = sample_players[0].id
        year = 2024
        current_date = date(2024, 6, 15)

        # Mock player effects
        mock_effect = GamePlayerEffect(game_id=chat_id, user_id=user_id)
        mocker.patch('bot.handlers.game.shop_service.get_or_create_player_effects', return_value=mock_effect)

        # Mock bank
        from bot.app.models import ChatBank
        mock_bank = ChatBank(game_id=chat_id, balance=0)
        mocker.patch('bot.handlers.game.transfer_service.get_or_create_chat_bank', return_value=mock_bank)

        # Mock can_afford to return True
        mocker.patch('bot.handlers.game.shop_service.can_afford', return_value=True)

        # Mock spend_coins to track the amount
        mock_spend = mocker.patch('bot.handlers.game.shop_service.spend_coins')

        # Buy immunity with custom price (5 instead of 10)
        success, message, commission = buy_immunity(
            mock_db_session, chat_id, user_id, year, current_date
        )

        assert success is True
        # Verify spend_coins was called with custom price (5)
        # spend_coins вызывается с параметрами: (db_session, game_id, user_id, amount, year, reason)
        mock_spend.assert_called_once()
        call_args = mock_spend.call_args[0]
        spent_amount = call_args[3]  # 4th argument (index 3) is amount
        assert spent_amount == 5, f"Should spend 5 coins (custom price), but spent {spent_amount}. Full call: {call_args}"


@pytest.mark.integration
def test_feature_flag_reroll_disabled(mock_db_session, mock_game, sample_players, reset_config, mocker):
    """
    Тест попытки использовать reroll при reroll_enabled=false.

    Проверяет, что при отключенном reroll возвращается ошибка.
    """
    # Create config with reroll disabled
    config_data = {
        "enabled_chats": [-123456],
        "test_chat_id": None,
        "defaults": {},
        "chat_overrides": {
            "-123456": {
                "reroll_enabled": False
            }
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG': temp_path}):
            mock_game.chat_id = -123456
            chat_id = mock_game.chat_id
            year = 2024
            day = 167

            # Try to check if reroll is available
            can_reroll_result = can_reroll(mock_db_session, chat_id, year, day)

            # Should return False because feature is disabled
            assert can_reroll_result is False, "Reroll should not be available when disabled"
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
def test_feature_flag_transfer_disabled(mock_db_session, mock_game, sample_players, reset_config, mocker):
    """
    Тест попытки использовать transfer при transfer_enabled=false.

    Проверяет, что при отключенном transfer возвращается ошибка.
    """
    # Create config with transfer disabled
    config_data = {
        "enabled_chats": [-123456],
        "test_chat_id": None,
        "defaults": {},
        "chat_overrides": {
            "-123456": {
                "transfer_enabled": False
            }
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG': temp_path}):
            mock_game.chat_id = -123456
            chat_id = mock_game.chat_id
            sender_id = sample_players[0].id
            receiver_id = sample_players[1].id
            amount = 10
            year = 2024

            # Mock dependencies
            from bot.app.models import ChatBank
            mock_bank = ChatBank(game_id=chat_id, balance=0)
            mocker.patch('bot.handlers.game.transfer_service.get_or_create_chat_bank', return_value=mock_bank)
            mocker.patch('bot.handlers.game.coin_service.get_balance', return_value=100)
            mocker.patch('bot.handlers.game.coin_service.add_coins')

            # Try to execute transfer - должен вызвать ValueError
            with pytest.raises(ValueError, match="Transfers are disabled"):
                execute_transfer(
                    mock_db_session, chat_id, sender_id, receiver_id, amount, year, 167
                )
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
def test_disabled_features_not_in_shop_menu(reset_config):
    """
    Тест, что отключенные фичи не отображаются в меню магазина.

    Проверяет, что при отключении фич они не показываются в UI.
    """
    # Create config with all features disabled
    config_data = {
        "enabled_chats": [-123456],
        "test_chat_id": None,
        "defaults": {},
        "chat_overrides": {
            "-123456": {
                "immunity_enabled": False,
                "double_chance_enabled": False,
                "prediction_enabled": False
            }
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG': temp_path}):
            config = get_config(-123456)

            # Generate shop menu
            shop_menu = get_shop_menu(config)

            # Verify disabled features are NOT in menu
            assert "Защита от пидора" not in shop_menu
            assert "Двойной шанс" not in shop_menu
            assert "Предсказание" not in shop_menu

            # Menu should still have header and balance placeholder
            assert "Магазин пидор" in shop_menu
            assert "баланс" in shop_menu.lower()
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
def test_disabled_features_not_in_keyboard(mock_game, sample_players, reset_config, mocker):
    """
    Тест, что кнопки отключенных фич не создаются в клавиатуре.

    Проверяет, что shop_helpers не создаёт кнопки для отключенных фич.
    """
    from bot.handlers.game.shop_helpers import create_shop_keyboard

    # Create config with some features disabled
    config_data = {
        "enabled_chats": [-123456],
        "test_chat_id": None,
        "defaults": {},
        "chat_overrides": {
            "-123456": {
                "immunity_enabled": False,
                "prediction_enabled": False,
                "double_chance_enabled": True  # Only this is enabled
            }
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG': temp_path}):
            mock_game.chat_id = -123456
            user = sample_players[0]

            # Create keyboard
            keyboard = create_shop_keyboard(user.tg_id, mock_game.chat_id)

            # Convert keyboard to list of button texts
            button_texts = []
            for row in keyboard.inline_keyboard:
                for button in row:
                    button_texts.append(button.text)

            # Verify only double_chance button is present
            assert any("Двойной шанс" in text for text in button_texts), "Double chance button should be present"
            assert not any("Защита" in text for text in button_texts), "Immunity button should NOT be present"
            assert not any("Предсказание" in text for text in button_texts), "Prediction button should NOT be present"
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
def test_feature_flag_give_coins_disabled(mock_db_session, mock_game, sample_players, reset_config, mocker):
    """
    Тест попытки использовать give_coins при give_coins_enabled=false.

    Проверяет, что при отключенном give_coins возвращается ошибка.
    """
    # Create config with give_coins disabled
    config_data = {
        "enabled_chats": [-123456],
        "test_chat_id": None,
        "defaults": {},
        "chat_overrides": {
            "-123456": {
                "give_coins_enabled": False
            }
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG': temp_path}):
            mock_game.chat_id = -123456
            chat_id = mock_game.chat_id
            user_id = sample_players[0].id
            winner_id = sample_players[1].id
            year = 2024
            day = 167

            # Mock has_claimed_today to return False
            mock_result = MagicMock()
            mock_result.first.return_value = None
            mock_db_session.exec.return_value = mock_result

            # Try to claim coins - должен вызвать ValueError
            with pytest.raises(ValueError, match="Give coins is disabled"):
                claim_coins(
                    mock_db_session, chat_id, user_id, year, day, is_winner=False
                )
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
def test_multiple_chats_different_configs(reset_config):
    """
    Тест, что разные чаты могут иметь разные конфигурации.

    Проверяет изоляцию конфигураций между чатами.
    """
    # Create config with different settings for different chats
    config_data = {
        "enabled_chats": [-111, -222],
        "test_chat_id": -222,
        "defaults": {
            "immunity_price": 10,
            "reroll_enabled": True
        },
        "chat_overrides": {
            "-111": {
                "immunity_price": 15,
                "reroll_enabled": False
            },
            "-222": {
                "immunity_price": 5,
                "transfer_enabled": False
            }
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG': temp_path}):
            # Get configs for both chats
            config1 = get_config(-111)
            config2 = get_config(-222)

            # Verify chat 1 has its own settings
            assert config1.chat_id == -111
            assert config1.is_test is False
            assert config1.constants.immunity_price == 15
            assert config1.constants.reroll_enabled is False
            assert config1.constants.transfer_enabled is True  # Default

            # Verify chat 2 has different settings
            assert config2.chat_id == -222
            assert config2.is_test is True
            assert config2.constants.immunity_price == 5
            assert config2.constants.reroll_enabled is True  # Default
            assert config2.constants.transfer_enabled is False

            # Verify configs are independent
            assert config1.constants.immunity_price != config2.constants.immunity_price
            assert config1.constants.reroll_enabled != config2.constants.reroll_enabled
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
def test_config_fallback_to_defaults(reset_config):
    """
    Тест fallback на значения по умолчанию для чата без переопределений.

    Проверяет, что чаты без переопределений используют дефолтные значения.
    """
    config_data = {
        "enabled_chats": [-111, -222],
        "test_chat_id": None,
        "defaults": {
            "immunity_price": 12,
            "coins_per_win": 5
        },
        "chat_overrides": {
            "-111": {
                "immunity_price": 20
            }
            # -222 has no overrides
        }
    }

    with NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(config_data, f)
        temp_path = f.name

    try:
        with patch.dict(os.environ, {'GAME_CONFIG': temp_path}):
            # Chat with overrides
            config1 = get_config(-111)
            assert config1.constants.immunity_price == 20  # Overridden
            assert config1.constants.coins_per_win == 5    # Default

            # Chat without overrides - should use all defaults
            config2 = get_config(-222)
            assert config2.constants.immunity_price == 12  # Default
            assert config2.constants.coins_per_win == 5    # Default
    finally:
        Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
def test_reroll_button_text_with_custom_price(custom_config_file, reset_config):
    """
    Тест, что текст кнопки перевыбора содержит правильную цену.

    Проверяет, что UI отображает кастомную цену перевыбора.
    """
    with patch.dict(os.environ, {'GAME_CONFIG': custom_config_file}):
        config = get_config(-4608252738)

        # Get reroll messages
        reroll_messages = get_reroll_messages(config)
        button_text = reroll_messages['button_text']

        # Verify custom price is in button text
        assert "10 💰" in button_text, f"Button should show custom price 10, got: {button_text}"
        assert "15 💰" not in button_text, "Button should NOT show default price 15"


@pytest.mark.integration
def test_immunity_messages_with_custom_price(custom_config_file, reset_config):
    """
    Тест, что сообщения о защите содержат правильную цену.

    Проверяет, что все сообщения используют кастомную цену.
    """
    with patch.dict(os.environ, {'GAME_CONFIG': custom_config_file}):
        config = get_config(-4608252738)

        # Get immunity messages
        immunity_messages = get_immunity_messages(config)

        # Check purchase success message
        assert "5 койнов" in immunity_messages['purchase_success']

        # Check error message
        assert "5 койнов" in immunity_messages['error_insufficient_funds']

        # Check item description
        assert "5 койнов" in immunity_messages['item_desc']


# Уверенность: 95%
#
# Создал полный набор интеграционных тестов для этапа 14, которые проверяют:
# 1. ✅ Полный цикл с переопределением констант для тестового чата
# 2. ✅ Корректность отображения цен в сообщениях
# 3. ✅ Работу магазина с кастомными ценами
# 4. ✅ Feature flags - попытки использовать отключенные фичи (reroll, transfer, give_coins)
# 5. ✅ Отсутствие отключенных фич в меню магазина
# 6. ✅ Отсутствие кнопок отключенных фич в клавиатуре
# 7. ✅ Изоляцию конфигураций между разными чатами
# 8. ✅ Fallback на дефолтные значения
# 9. ✅ Правильные цены в UI элементах (кнопки, сообщения)
#
# Тесты следуют структуре существующих интеграционных тестов и покрывают все требования из плана.
