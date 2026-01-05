"""Tests for pidorcoins commands."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from telegram import Update, User, Chat
from telegram.ext import CallbackContext

from bot.handlers.game.commands import pidorcoinsme_cmd, pidorcoinsstats_cmd, pidorcoinsall_cmd
from bot.app.models import TGUser, Game, PidorCoinTransaction
from bot.handlers.game.coin_service import get_balance, get_leaderboard, get_leaderboard_by_year


@pytest.fixture
def mock_update():
    """Create a mock Update object."""
    update = MagicMock(spec=Update)
    update.effective_chat = MagicMock(spec=Chat)
    update.effective_chat.id = 12345
    update.effective_chat.send_message = AsyncMock()
    return update


@pytest.fixture
def mock_context(mock_db_session, sample_players):
    """Create a mock CallbackContext with game and tg_user."""
    context = MagicMock(spec=CallbackContext)
    context.db_session = mock_db_session
    context.tg_user = sample_players[0]  # First player
    context.game = MagicMock(spec=Game)
    context.game.id = 1
    context.game.players = sample_players
    return context


@pytest.mark.asyncio
async def test_pidorcoinsme_cmd_shows_balance(mock_update, mock_context, mock_db_session, sample_players):
    """Test that pidorcoinsme_cmd shows user's balance."""
    # Mock the get_balance function to return a specific value
    mock_db_session.exec.return_value.first.return_value = (100,)

    await pidorcoinsme_cmd(mock_update, mock_context)

    # Verify that send_message was called with the correct message
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = mock_update.effective_chat.send_message.call_args
    assert "100" in call_args[0][0]  # Check that balance is in the message
    assert "MarkdownV2" in call_args[1]["parse_mode"]


@pytest.mark.asyncio
async def test_pidorcoinsme_cmd_zero_balance(mock_update, mock_context, mock_db_session, sample_players):
    """Test that pidorcoinsme_cmd shows zero balance correctly."""
    # Mock the get_balance function to return 0
    mock_db_session.exec.return_value.first.return_value = (0,)

    await pidorcoinsme_cmd(mock_update, mock_context)

    # Verify that send_message was called with the correct message
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = mock_update.effective_chat.send_message.call_args
    assert "0" in call_args[0][0]  # Check that zero balance is in the message
    assert "MarkdownV2" in call_args[1]["parse_mode"]


@pytest.mark.asyncio
async def test_pidorcoinsstats_cmd_shows_leaderboard(mock_update, mock_context, mock_db_session, sample_players):
    """Test that pidorcoinsstats_cmd shows leaderboard for current year."""
    # Mock the get_leaderboard_by_year function to return sample data
    leaderboard_data = [
        (sample_players[0], 150),
        (sample_players[1], 100),
        (sample_players[2], 50)
    ]
    mock_db_session.exec.return_value.all.return_value = leaderboard_data

    await pidorcoinsstats_cmd(mock_update, mock_context)

    # Verify that send_message was called with the correct message
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = mock_update.effective_chat.send_message.call_args
    assert "Топ\\-50" in call_args[0][0]  # Check that leaderboard header is in the message
    assert "150" in call_args[0][0]  # Check that top player's coins are in the message
    assert "MarkdownV2" in call_args[1]["parse_mode"]


@pytest.mark.asyncio
async def test_pidorcoinsstats_cmd_empty(mock_update, mock_context, mock_db_session, sample_players):
    """Test that pidorcoinsstats_cmd handles empty leaderboard correctly."""
    # Mock the get_leaderboard_by_year function to return empty list
    mock_db_session.exec.return_value.all.return_value = []

    await pidorcoinsstats_cmd(mock_update, mock_context)

    # Verify that send_message was called with the empty message
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = mock_update.effective_chat.send_message.call_args
    assert "нет пидор\\-койнов" in call_args[0][0]  # Check that empty message is shown
    assert "MarkdownV2" in call_args[1]["parse_mode"]


@pytest.mark.asyncio
async def test_pidorcoinsall_cmd_shows_leaderboard(mock_update, mock_context, mock_db_session, sample_players):
    """Test that pidorcoinsall_cmd shows all-time leaderboard."""
    # Mock the get_leaderboard function to return sample data
    leaderboard_data = [
        (sample_players[0], 300),
        (sample_players[1], 200),
        (sample_players[2], 100)
    ]
    mock_db_session.exec.return_value.all.return_value = leaderboard_data

    await pidorcoinsall_cmd(mock_update, mock_context)

    # Verify that send_message was called with the correct message
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = mock_update.effective_chat.send_message.call_args
    assert "Топ\\-50" in call_args[0][0]  # Check that leaderboard header is in the message
    assert "300" in call_args[0][0]  # Check that top player's coins are in the message
    assert "MarkdownV2" in call_args[1]["parse_mode"]


@pytest.mark.asyncio
async def test_pidorcoinsall_cmd_empty(mock_update, mock_context, mock_db_session, sample_players):
    """Test that pidorcoinsall_cmd handles empty leaderboard correctly."""
    # Mock the get_leaderboard function to return empty list
    mock_db_session.exec.return_value.all.return_value = []

    await pidorcoinsall_cmd(mock_update, mock_context)

    # Verify that send_message was called with the empty message
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = mock_update.effective_chat.send_message.call_args
    assert "нет пидор\\-койнов" in call_args[0][0]  # Check that empty message is shown
    assert "MarkdownV2" in call_args[1]["parse_mode"]
