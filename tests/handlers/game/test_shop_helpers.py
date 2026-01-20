"""Tests for shop helpers functionality."""
import pytest
from unittest.mock import MagicMock, Mock
from telegram import InlineKeyboardMarkup

from bot.handlers.game.shop_helpers import (
    format_shop_callback_data,
    parse_shop_callback_data,
    create_shop_keyboard,
    create_prediction_keyboard,
    format_shop_menu_message,
    SHOP_CALLBACK_PREFIX
)
from bot.app.models import TGUser


@pytest.mark.unit
def test_format_shop_callback_data():
    """Test formatting callback_data for shop button."""
    # Test basic formatting
    result = format_shop_callback_data('immunity', 123)
    assert result == "shop_immunity_123"

    # Test with different item types
    result = format_shop_callback_data('double', 456)
    assert result == "shop_double_456"

    result = format_shop_callback_data('predict', 789)
    assert result == "shop_predict_789"


@pytest.mark.unit
def test_parse_shop_callback_data():
    """Test parsing callback_data to extract item_type and owner_user_id."""
    # Test valid callback_data
    item_type, owner_user_id = parse_shop_callback_data("shop_immunity_123")
    assert item_type == "immunity"
    assert owner_user_id == 123

    # Test with different values
    item_type, owner_user_id = parse_shop_callback_data("shop_double_456")
    assert item_type == "double"
    assert owner_user_id == 456

    # Test with large IDs
    item_type, owner_user_id = parse_shop_callback_data("shop_predict_999999")
    assert item_type == "predict"
    assert owner_user_id == 999999


@pytest.mark.unit
def test_parse_shop_callback_data_invalid_format():
    """Test parsing invalid callback_data raises ValueError."""
    # Test without prefix
    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_shop_callback_data("invalid_immunity_123")

    # Test with wrong number of parts
    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_shop_callback_data("shop_immunity")

    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_shop_callback_data("shop_immunity_123_456")

    # Test with non-numeric user_id
    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_shop_callback_data("shop_immunity_abc")

    # Test empty string
    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_shop_callback_data("")


@pytest.mark.unit
def test_create_shop_keyboard():
    """Test creating shop keyboard with item buttons."""
    # Setup
    owner_user_id = 123

    # Execute
    keyboard = create_shop_keyboard(owner_user_id)

    # Verify structure
    assert isinstance(keyboard, InlineKeyboardMarkup)
    assert len(keyboard.inline_keyboard) == 5  # 5 items (immunity, double, predict, transfer, bank)

    # Verify each item is on separate row
    for row in keyboard.inline_keyboard:
        assert len(row) == 1  # One button per row

    # Verify button texts contain item names and prices
    button_texts = [row[0].text for row in keyboard.inline_keyboard]
    assert any("🛡️ Защита от пидора" in text for text in button_texts)
    assert any("🎲 Двойной шанс" in text for text in button_texts)
    assert any("🔮 Предсказание" in text for text in button_texts)
    assert any("10 🪙" in text for text in button_texts)
    assert any("8 🪙" in text for text in button_texts)
    assert any("3 🪙" in text for text in button_texts)

    # Verify callback_data contains owner_user_id
    callback_data_list = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert all(str(owner_user_id) in cd for cd in callback_data_list)
    assert any("shop_immunity_" in cd for cd in callback_data_list)
    assert any("shop_double_" in cd for cd in callback_data_list)
    assert any("shop_predict_" in cd for cd in callback_data_list)


@pytest.mark.unit
def test_create_prediction_keyboard():
    """Test creating prediction keyboard with player buttons."""
    # Create mock players
    player1 = Mock(spec=TGUser)
    player1.id = 1
    player1.first_name = "Alice"
    player1.last_name = "Smith"

    player2 = Mock(spec=TGUser)
    player2.id = 2
    player2.first_name = "Bob"
    player2.last_name = None

    player3 = Mock(spec=TGUser)
    player3.id = 3
    player3.first_name = "Charlie"
    player3.last_name = "Brown"

    players = [player1, player2, player3]
    owner_user_id = 123
    candidates_count = 1  # For 3 players, ceil(3/10) = 1

    # Execute
    keyboard = create_prediction_keyboard(players, owner_user_id, candidates_count)

    # Verify structure - now includes player buttons + confirm/cancel buttons
    assert isinstance(keyboard, InlineKeyboardMarkup)
    # 3 player buttons (one per row) + 1 confirm button + 1 cancel button = 5 rows
    assert len(keyboard.inline_keyboard) >= 3  # At least player buttons

    # Verify button texts contain player names
    all_buttons = []
    for row in keyboard.inline_keyboard:
        all_buttons.extend(row)

    button_texts = [button.text for button in all_buttons]
    assert any("Alice Smith" in text for text in button_texts)
    assert any("Bob" in text for text in button_texts)
    assert any("Charlie Brown" in text for text in button_texts)


@pytest.mark.unit
def test_create_prediction_keyboard_single_player():
    """Test creating prediction keyboard with single player."""
    # Create mock player
    player1 = Mock(spec=TGUser)
    player1.id = 1
    player1.first_name = "Alice"
    player1.last_name = "Smith"

    players = [player1]
    owner_user_id = 456
    candidates_count = 1  # For 1 player, ceil(1/10) = 1

    # Execute
    keyboard = create_prediction_keyboard(players, owner_user_id, candidates_count)

    # Verify structure - at least 1 player button
    assert len(keyboard.inline_keyboard) >= 1

    # Verify button text contains player name
    all_buttons = []
    for row in keyboard.inline_keyboard:
        all_buttons.extend(row)

    button_texts = [button.text for button in all_buttons]
    assert any("Alice Smith" in text for text in button_texts)


@pytest.mark.unit
def test_create_prediction_keyboard_many_players():
    """Test creating prediction keyboard with many players."""
    # Create 10 mock players
    players = []
    for i in range(1, 11):
        player = Mock(spec=TGUser)
        player.id = i
        player.first_name = f"Player{i}"
        player.last_name = None
        players.append(player)

    owner_user_id = 789
    candidates_count = 1  # For 10 players, ceil(10/10) = 1

    # Execute
    keyboard = create_prediction_keyboard(players, owner_user_id, candidates_count)

    # Verify structure - buttons are now grouped by 2 per row
    # 10 players = 5 rows of players + 1 row for status button + 1 row for cancel = 7 rows minimum
    assert len(keyboard.inline_keyboard) >= 5  # At least 5 rows of player buttons

    # Verify all players are present
    all_buttons = []
    for row in keyboard.inline_keyboard:
        all_buttons.extend(row)

    button_texts = [button.text for button in all_buttons]
    for i in range(1, 11):
        assert any(f"Player{i}" in text for text in button_texts)


@pytest.mark.unit
def test_format_shop_menu_message():
    """Test formatting shop menu message."""
    # Test with zero balance
    result = format_shop_menu_message(0)
    assert "🏪 *Магазин пидор\\-койнов*" in result
    assert "💰 Ваш баланс: *0* 🪙" in result
    assert "🛡️ Защита от пидора" in result
    assert "🎲 Двойной шанс" in result
    assert "🔮 Предсказание" in result
    assert "*10* 🪙" in result
    assert "*8* 🪙" in result
    assert "*3* 🪙" in result
    assert "_Выберите товар для покупки:_" in result

    # Test with positive balance
    result = format_shop_menu_message(100)
    assert "💰 Ваш баланс: *100* 🪙" in result

    # Test with large balance (format_number may or may not add spaces)
    result = format_shop_menu_message(1000000)
    # Just verify the balance is present, format may vary
    assert "💰 Ваш баланс:" in result
    assert "1000000" in result or "1 000 000" in result


@pytest.mark.unit
def test_format_shop_menu_message_markdown_escaping():
    """Test that shop menu message properly escapes Markdown V2 characters."""
    result = format_shop_menu_message(50)

    # Verify proper escaping
    assert "\\-" in result  # Hyphens escaped
    assert "\\(" in result  # Parentheses escaped
    assert "\\)" in result

    # Verify no unescaped special characters (except allowed ones)
    # Allowed: * _ [ ] ( ) ~ ` > # + - = | { } . !
    # But they must be escaped in text (not in formatting)
    assert "*Магазин пидор\\-койнов*" in result  # * for bold, - escaped
    assert "_Выберите товар для покупки:_" in result  # _ for italic


@pytest.mark.unit
def test_shop_callback_prefix_constant():
    """Test SHOP_CALLBACK_PREFIX constant value."""
    assert SHOP_CALLBACK_PREFIX == 'shop_'


@pytest.mark.unit
def test_format_and_parse_roundtrip():
    """Test that format and parse are inverse operations."""
    # Test roundtrip for different values
    test_cases = [
        ('immunity', 123),
        ('double', 456),
        ('predict', 789),
        ('immunity', 1),
        ('double', 999999)
    ]

    for item_type, owner_user_id in test_cases:
        # Format
        callback_data = format_shop_callback_data(item_type, owner_user_id)

        # Parse
        parsed_item_type, parsed_owner_user_id = parse_shop_callback_data(callback_data)

        # Verify roundtrip
        assert parsed_item_type == item_type
        assert parsed_owner_user_id == owner_user_id
