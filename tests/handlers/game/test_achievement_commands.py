"""Tests for achievement commands."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from telegram import Update, User, Chat, CallbackQuery
from telegram.ext import CallbackContext

from bot.handlers.game.commands import handle_shop_achievements_callback
from bot.app.models import TGUser, Game, UserAchievement
from bot.handlers.game.achievement_constants import ACHIEVEMENTS


@pytest.fixture
def mock_update():
    """Create a mock Update object with callback query."""
    update = MagicMock(spec=Update)
    update.effective_chat = MagicMock(spec=Chat)
    update.effective_chat.id = 12345
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = 100
    update.effective_user.username = "testuser"

    # Create callback query
    query = MagicMock(spec=CallbackQuery)
    query.from_user = MagicMock(spec=User)
    query.from_user.id = 100
    query.from_user.username = "testuser"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "shop_achievements_100"

    update.callback_query = query
    return update


@pytest.fixture
def mock_context(mock_db_session, sample_players):
    """Create a mock CallbackContext with game and tg_user."""
    context = MagicMock(spec=CallbackContext)
    context.db_session = mock_db_session
    context.tg_user = sample_players[0]  # First player (id=100)

    # Create a proper mock for game
    game_mock = MagicMock(spec=Game)
    game_mock.id = 1

    context.game = game_mock
    context.bot = MagicMock()
    return context


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_achievements_callback_no_achievements(mock_update, mock_context, mock_db_session):
    """Test achievements view when user has no achievements."""
    # Mock get_user_achievements to return empty list
    with patch('bot.handlers.game.achievement_service.get_user_achievements', return_value=[]):
        await handle_shop_achievements_callback(mock_update, mock_context)

    # Verify that answer was called
    mock_update.callback_query.answer.assert_called_once()

    # Verify that edit_message_text was called
    mock_update.callback_query.edit_message_text.assert_called_once()
    call_args = mock_update.callback_query.edit_message_text.call_args

    # Check that message contains empty state text
    assert "пока нет достижений" in call_args[1]["text"]
    assert call_args[1]["parse_mode"] == "MarkdownV2"
    # Check that reply_markup (back button) is present
    assert "reply_markup" in call_args[1]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_achievements_callback_with_achievements(mock_update, mock_context, mock_db_session, sample_players):
    """Test achievements view when user has some achievements."""
    # Create mock achievements
    achievement1 = UserAchievement(
        id=1,
        game_id=1,
        user_id=100,
        achievement_code="first_blood",
        year=2024,
        period=None,
        earned_at=datetime(2024, 1, 15, 12, 0, 0)
    )

    achievement2 = UserAchievement(
        id=2,
        game_id=1,
        user_id=100,
        achievement_code="streak_3",
        year=2024,
        period=None,
        earned_at=datetime(2024, 2, 20, 14, 30, 0)
    )

    # Mock get_user_achievements to return achievements
    with patch('bot.handlers.game.achievement_service.get_user_achievements', return_value=[achievement1, achievement2]):
        await handle_shop_achievements_callback(mock_update, mock_context)

    # Verify that answer was called
    mock_update.callback_query.answer.assert_called_once()

    # Verify that edit_message_text was called
    mock_update.callback_query.edit_message_text.assert_called_once()
    call_args = mock_update.callback_query.edit_message_text.call_args

    message_text = call_args[1]["text"]

    # Check that message contains achievement names
    assert "Первая кровь" in message_text
    assert "Снайпер" in message_text

    # Check that message contains earned achievements (✅)
    assert "✅" in message_text

    # Check that message contains not earned achievements (⬜)
    assert "⬜" in message_text

    # Check that total coins is shown
    assert "Всего заработано" in message_text
    # first_blood (10) + streak_3 (20) = 30
    assert "30" in message_text

    assert call_args[1]["parse_mode"] == "MarkdownV2"
    # Check that reply_markup (back button) is present
    assert "reply_markup" in call_args[1]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_achievements_callback_shows_total_coins(mock_update, mock_context, mock_db_session):
    """Test that achievements view shows total earned coins."""
    # Create mock achievements with all possible achievements
    achievements = [
        UserAchievement(
            id=i+1,
            game_id=1,
            user_id=100,
            achievement_code=code,
            year=2024,
            period=None,
            earned_at=datetime(2024, 1, i+1, 12, 0, 0)
        )
        for i, code in enumerate(ACHIEVEMENTS.keys())
    ]

    # Mock get_user_achievements to return all achievements
    with patch('bot.handlers.game.achievement_service.get_user_achievements', return_value=achievements):
        await handle_shop_achievements_callback(mock_update, mock_context)

    # Verify that edit_message_text was called
    call_args = mock_update.callback_query.edit_message_text.call_args
    message_text = call_args[1]["text"]

    # Calculate expected total: 10 + 20 + 30 + 50 = 110
    expected_total = sum(ACHIEVEMENTS[code]['reward'] for code in ACHIEVEMENTS.keys())

    # Check that total is shown
    assert "Всего заработано" in message_text
    assert str(expected_total) in message_text


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_achievements_callback_not_owner(mock_update, mock_context, mock_db_session):
    """Test that non-owner cannot view achievements."""
    # Change callback query user to different user
    mock_update.callback_query.from_user.id = 200
    mock_update.callback_query.data = "shop_achievements_100"  # Owner is 100

    await handle_shop_achievements_callback(mock_update, mock_context)

    # Verify error response
    mock_update.callback_query.answer.assert_called_once()
    call_args = mock_update.callback_query.answer.call_args
    assert "❌" in call_args[0][0] or "не твой" in call_args[0][0].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_achievements_callback_shows_all_achievements(mock_update, mock_context, mock_db_session):
    """Test that all achievements (earned and not earned) are shown."""
    # Create only one achievement
    achievement = UserAchievement(
        id=1,
        game_id=1,
        user_id=100,
        achievement_code="first_blood",
        year=2024,
        period=None,
        earned_at=datetime(2024, 1, 15, 12, 0, 0)
    )

    # Mock get_user_achievements to return single achievement
    with patch('bot.handlers.game.achievement_service.get_user_achievements', return_value=[achievement]):
        await handle_shop_achievements_callback(mock_update, mock_context)

    # Verify that edit_message_text was called
    call_args = mock_update.callback_query.edit_message_text.call_args
    message_text = call_args[1]["text"]

    # Check that all achievement names are present
    for achievement_data in ACHIEVEMENTS.values():
        assert achievement_data['name'] in message_text

    # Check that earned achievement has ✅
    assert "✅" in message_text

    # Check that not earned achievements have ⬜
    # Count should be: total achievements - 1 earned
    not_earned_count = message_text.count("⬜")
    assert not_earned_count == len(ACHIEVEMENTS) - 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_achievements_callback_has_back_button(mock_update, mock_context, mock_db_session):
    """Test that achievements view has back button."""
    # Mock get_user_achievements to return empty list
    with patch('bot.handlers.game.achievement_service.get_user_achievements', return_value=[]):
        await handle_shop_achievements_callback(mock_update, mock_context)

    # Verify that edit_message_text was called with reply_markup
    call_args = mock_update.callback_query.edit_message_text.call_args

    # Check that reply_markup is present
    assert "reply_markup" in call_args[1]

    # Check that keyboard has back button
    keyboard = call_args[1]["reply_markup"]
    assert keyboard is not None
    assert len(keyboard.inline_keyboard) > 0

    # Check that button text contains "Назад"
    button = keyboard.inline_keyboard[0][0]
    assert "Назад" in button.text or "⬅️" in button.text
