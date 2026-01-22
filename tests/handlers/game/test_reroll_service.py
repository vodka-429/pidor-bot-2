"""Tests for reroll service functionality."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from bot.handlers.game.reroll_service import (
    can_reroll,
    execute_reroll,
    remove_reroll_button_after_timeout,
    REROLL_PRICE
)
from bot.handlers.game.commands import COINS_PER_WIN
from bot.app.models import GameResult, TGUser


@pytest.mark.unit
def test_can_reroll_returns_true_when_available(mock_db_session):
    """Test can_reroll returns True when reroll is available."""
    # Setup
    game_id = 1
    year = 2024
    day = 100

    # Mock GameResult with reroll available
    mock_game_result = MagicMock()
    mock_game_result.reroll_available = True

    mock_result = MagicMock()
    mock_result.first.return_value = mock_game_result
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = can_reroll(mock_db_session, game_id, year, day)

    # Verify
    assert result is True
    mock_db_session.exec.assert_called_once()


@pytest.mark.unit
def test_can_reroll_returns_false_when_not_available(mock_db_session):
    """Test can_reroll returns False when reroll is not available."""
    # Setup
    game_id = 1
    year = 2024
    day = 100

    # Mock GameResult with reroll not available
    mock_game_result = MagicMock()
    mock_game_result.reroll_available = False

    mock_result = MagicMock()
    mock_result.first.return_value = mock_game_result
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = can_reroll(mock_db_session, game_id, year, day)

    # Verify
    assert result is False


@pytest.mark.unit
def test_can_reroll_returns_false_when_game_result_not_found(mock_db_session):
    """Test can_reroll returns False when GameResult doesn't exist."""
    # Setup
    game_id = 1
    year = 2024
    day = 100

    # Mock no GameResult found
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = can_reroll(mock_db_session, game_id, year, day)

    # Verify
    assert result is False


@pytest.mark.unit
def test_execute_reroll_updates_game_result(mock_db_session, sample_players):
    """Test execute_reroll updates GameResult with new winner."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id
    mock_game_result.reroll_available = True

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        # First call - get GameResult
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            # Second call - get old winner
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    with patch('bot.handlers.game.reroll_service.spend_coins') as mock_spend, \
         patch('bot.handlers.game.reroll_service.add_coins') as mock_add, \
         patch('random.choice', return_value=sample_players[1]):

        old_winner_result, new_winner_result = execute_reroll(
            mock_db_session, game_id, year, day, initiator_id, sample_players
        )

    # Verify spend_coins was called
    mock_spend.assert_called_once_with(
        mock_db_session, game_id, initiator_id, REROLL_PRICE, year, "reroll", auto_commit=False
    )

    # Verify add_coins was called for new winner
    mock_add.assert_called_once_with(
        mock_db_session, game_id, sample_players[1].id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify GameResult was updated
    assert mock_game_result.original_winner_id == old_winner_id
    assert mock_game_result.winner_id == sample_players[1].id
    assert mock_game_result.reroll_available is False
    assert mock_game_result.reroll_initiator_id == initiator_id

    # Verify commit was called
    mock_db_session.commit.assert_called_once()

    # Verify returned values
    assert old_winner_result == old_winner
    assert new_winner_result == sample_players[1]


@pytest.mark.unit
def test_execute_reroll_allows_same_winner(mock_db_session, sample_players):
    """Test execute_reroll allows the same person to win again (double reward)."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute - same player wins again
    with patch('bot.handlers.game.reroll_service.spend_coins'), \
         patch('bot.handlers.game.reroll_service.add_coins') as mock_add, \
         patch('random.choice', return_value=old_winner):

        old_winner_result, new_winner_result = execute_reroll(
            mock_db_session, game_id, year, day, initiator_id, sample_players
        )

    # Verify add_coins was called even for the same winner (double reward)
    mock_add.assert_called_once_with(
        mock_db_session, game_id, old_winner.id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify both returned winners are the same
    assert old_winner_result == old_winner
    assert new_winner_result == old_winner


@pytest.mark.unit
def test_execute_reroll_raises_error_when_no_players(mock_db_session):
    """Test execute_reroll raises ValueError when players list is empty."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    players = []

    # Execute and verify
    with pytest.raises(ValueError, match="Players list cannot be empty"):
        execute_reroll(mock_db_session, game_id, year, day, initiator_id, players)


@pytest.mark.unit
def test_execute_reroll_raises_error_when_game_result_not_found(mock_db_session, sample_players):
    """Test execute_reroll raises ValueError when GameResult doesn't exist."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2

    # Mock no GameResult found
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Execute and verify
    with pytest.raises(ValueError, match="GameResult not found"):
        execute_reroll(mock_db_session, game_id, year, day, initiator_id, sample_players)


@pytest.mark.unit
def test_execute_reroll_raises_error_when_old_winner_not_found(mock_db_session, sample_players):
    """Test execute_reroll raises ValueError when old winner doesn't exist."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 999  # Non-existent user

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            # Old winner not found
            mock_result.first.return_value = None

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute and verify
    with pytest.raises(ValueError, match="Old winner with id .* not found"):
        execute_reroll(mock_db_session, game_id, year, day, initiator_id, sample_players)


@pytest.mark.asyncio
async def test_remove_reroll_button_after_timeout_removes_button():
    """Test remove_reroll_button_after_timeout removes button after delay."""
    # Setup
    mock_bot = MagicMock()
    mock_bot.edit_message_reply_markup = AsyncMock()
    chat_id = 123456
    message_id = 789
    delay_minutes = 0.001  # Very short delay for testing

    # Execute
    await remove_reroll_button_after_timeout(mock_bot, chat_id, message_id, delay_minutes)

    # Verify
    mock_bot.edit_message_reply_markup.assert_called_once_with(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=None
    )


@pytest.mark.asyncio
async def test_remove_reroll_button_handles_exception():
    """Test remove_reroll_button_after_timeout handles exceptions gracefully."""
    # Setup
    mock_bot = MagicMock()
    mock_bot.edit_message_reply_markup = AsyncMock(side_effect=Exception("Message deleted"))
    chat_id = 123456
    message_id = 789
    delay_minutes = 0.001

    # Execute - should not raise exception
    await remove_reroll_button_after_timeout(mock_bot, chat_id, message_id, delay_minutes)

    # Verify the call was attempted
    mock_bot.edit_message_reply_markup.assert_called_once()


@pytest.mark.unit
def test_execute_reroll_preserves_old_winner_coins(mock_db_session, sample_players):
    """Test execute_reroll does NOT remove coins from old winner."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    with patch('bot.handlers.game.reroll_service.spend_coins') as mock_spend, \
         patch('bot.handlers.game.reroll_service.add_coins') as mock_add, \
         patch('random.choice', return_value=sample_players[1]):

        execute_reroll(mock_db_session, game_id, year, day, initiator_id, sample_players)

    # Verify spend_coins was called ONLY for initiator, NOT for old winner
    assert mock_spend.call_count == 1
    mock_spend.assert_called_with(
        mock_db_session, game_id, initiator_id, REROLL_PRICE, year, "reroll", auto_commit=False
    )

    # Verify add_coins was called ONLY for new winner
    assert mock_add.call_count == 1
    mock_add.assert_called_with(
        mock_db_session, game_id, sample_players[1].id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )
