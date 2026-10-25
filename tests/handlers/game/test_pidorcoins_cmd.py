"""Tests for pidorcoins commands."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from telegram import Update, User, Chat
from telegram.ext import CallbackContext

from bot.handlers.game.commands import pidorcoinsme_cmd, pidorcoinsstats_cmd
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

    with patch("bot.handlers.game.coin_service.get_open_deposit_amounts", return_value={}):
        await pidorcoinsstats_cmd(mock_update, mock_context)

    # Verify that send_message was called with the correct message
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = mock_update.effective_chat.send_message.call_args
    assert "Топ\\-50" in call_args[0][0]  # Check that leaderboard header is in the message
    assert "150" in call_args[0][0]  # Check that top player's coins are in the message
    assert "MarkdownV2" in call_args[1]["parse_mode"]


@pytest.mark.asyncio
async def test_pidorcoinsstats_cmd_marks_only_players_with_deposit(mock_update, mock_context, mock_db_session, sample_players):
    """Только у игрока с открытым вкладом есть пометка 💼, а его сумма включает тело вклада."""
    # Годовые суммы по транзакциям; патч вкладов виден и в get_leaderboard_by_year_with_deposits,
    # поэтому у игрока 2 итог 50 + 100 = 150
    mock_db_session.exec.return_value.all.return_value = [
        (sample_players[0], 150),
        (sample_players[1], 50),
        (sample_players[2], 50),
    ]

    with patch("bot.handlers.game.coin_service.get_open_deposit_amounts", return_value={sample_players[1].id: 100}):
        await pidorcoinsstats_cmd(mock_update, mock_context)

    text = mock_update.effective_chat.send_message.call_args[0][0]
    assert text.count("💼") == 1
    lines = text.split("\n")
    depositor = next(item for item in lines if "player2" in item)
    assert "150 койн" in depositor and "\\(💼 100\\)" in depositor
    for name in ("player1", "player3"):
        assert "💼" not in next(item for item in lines if name in item)
    assert "50 койн" in next(item for item in lines if "player3" in item)


@pytest.mark.asyncio
async def test_pidorcoinsstats_cmd_empty(mock_update, mock_context, mock_db_session, sample_players):
    """Test that pidorcoinsstats_cmd handles empty leaderboard correctly."""
    # Mock the get_leaderboard_by_year function to return empty list
    mock_db_session.exec.return_value.all.return_value = []

    with patch("bot.handlers.game.coin_service.get_open_deposit_amounts", return_value={}):
        await pidorcoinsstats_cmd(mock_update, mock_context)

    # Verify that send_message was called with the empty message
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = mock_update.effective_chat.send_message.call_args
    assert "нет пидор\\-койнов" in call_args[0][0]  # Check that empty message is shown
    assert "MarkdownV2" in call_args[1]["parse_mode"]




@pytest.mark.asyncio
async def test_pidorcoinsme_cmd_shows_open_deposit(mock_update, mock_context, mock_db_session, sample_players):
    """An open deposit adds a line with its amount and maturity date (MarkdownV2-escaped)."""
    from datetime import date
    from types import SimpleNamespace

    mock_db_session.exec.return_value.first.return_value = (100,)
    deposit = SimpleNamespace(amount=70, matures_on=date(2026, 6, 15))

    with patch("bot.handlers.game.coin_service.get_open_deposit_amounts", return_value={sample_players[0].id: 70}), \
            patch("bot.handlers.game.deposit_service.get_open_deposit", return_value=deposit), \
            patch("bot.handlers.game.shop_helpers.format_date_readable", return_value="15.06"):
        await pidorcoinsme_cmd(mock_update, mock_context)

    text = mock_update.effective_chat.send_message.call_args[0][0]
    assert "На вкладе: *70* до 15\\.06" in text
    assert "100" in text
