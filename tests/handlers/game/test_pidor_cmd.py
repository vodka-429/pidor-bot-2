"""Tests for pidor_cmd command."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, call, patch
from bot.handlers.game.commands import pidor_cmd
from bot.handlers.game.text_static import (
    ERROR_NOT_ENOUGH_PLAYERS,
    CURRENT_DAY_GAME_RESULT,
)


@pytest.mark.unit
def test_pidor_cmd_not_enough_players(mock_update, mock_context, mock_game):
    """Test that error is sent when there are less than 2 players."""
    # Setup: game with only 1 player
    mock_player = MagicMock()
    mock_game.players = [mock_player]
    mock_context.game = mock_game
    
    # Execute
    pidor_cmd(mock_update, mock_context)
    
    # Verify
    mock_update.effective_chat.send_message.assert_called_once_with(ERROR_NOT_ENOUGH_PLAYERS)


@pytest.mark.unit
def test_pidor_cmd_existing_result_today(mock_update, mock_context, mock_game, mocker):
    """Test that existing result message is sent when game was already played today."""
    # Setup: game with enough players
    mock_player1 = MagicMock()
    mock_player1.full_username.return_value = "@Player1"
    mock_player2 = MagicMock()
    mock_player2.full_username.return_value = "@Player2"
    
    mock_game.players = [mock_player1, mock_player2]
    mock_context.game = mock_game
    
    # Mock existing result for today
    mock_result = MagicMock()
    mock_result.winner = mock_player1
    
    # Mock the query chain for both Game (in decorator) and GameResult (in function)
    # First call is for Game in ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Second call is for GameResult in pidor_cmd
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = mock_result
    
    # Setup query to return different results for Game and GameResult
    mock_context.db_session.query.side_effect = [mock_game_query, mock_result_query]
    
    # Execute
    pidor_cmd(mock_update, mock_context)
    
    # Verify that reply_markdown_v2 was called with the existing result message
    mock_update.message.reply_markdown_v2.assert_called_once()
    call_args = str(mock_update.message.reply_markdown_v2.call_args)
    assert "Player1" in call_args or CURRENT_DAY_GAME_RESULT[:20] in call_args


@pytest.mark.unit
def test_pidor_cmd_new_game_result(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that new game result is created and 4 stage messages are sent."""
    # Setup: game with enough players and no result for today
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain for both Game (in decorator) and GameResult (in function)
    # First call is for Game in ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Second call is for GameResult in pidor_cmd - should return None (no existing result)
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None
    
    # Setup query to return different results for Game and GameResult
    mock_context.db_session.query.side_effect = [mock_game_query, mock_result_query]
    
    # Mock random.choice to return first player and phrases
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        sample_players[0],  # winner selection
        "Stage 1 message",  # stage1 phrase
        "Stage 2 message",  # stage2 phrase
        "Stage 3 message",  # stage3 phrase
        "Stage 4 message: {username}",  # stage4 phrase
    ])
    
    # Mock time.sleep to avoid delays
    mocker.patch('bot.handlers.game.commands.time.sleep')
    
    # Mock current_datetime to return a non-last-day date
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidor_cmd(mock_update, mock_context)
    
    # Verify that 4 messages were sent (stage1-4)
    assert mock_update.effective_chat.send_message.call_count == 4
    
    # Verify that game result was appended
    mock_game.results.append.assert_called_once()
    
    # Verify that db session was committed
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.unit
def test_pidor_cmd_last_day_of_year(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that year results announcement is sent on December 31."""
    # Setup: game with enough players
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_result_query]
    
    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        sample_players[0],
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
    ])
    
    # Mock time.sleep
    mocker.patch('bot.handlers.game.commands.time.sleep')
    
    # Mock current_datetime to return December 31
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 31
    mock_dt.timetuple.return_value.tm_yday = 366
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidor_cmd(mock_update, mock_context)
    
    # Verify that 5 messages were sent (year announcement + 4 stages)
    assert mock_update.effective_chat.send_message.call_count == 5
    
    # Verify year announcement was sent
    calls = mock_update.effective_chat.send_message.call_args_list
    first_call_str = str(calls[0])
    assert "2024" in first_call_str or "Новым Годом" in first_call_str


@pytest.mark.unit
def test_pidor_cmd_random_winner_selection(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that winner is randomly selected from players list."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_result_query]
    
    # Mock random.choice and capture the call
    mock_random_choice = mocker.patch('bot.handlers.game.commands.random.choice')
    mock_random_choice.side_effect = [
        sample_players[1],  # winner
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
    ]
    
    # Mock time.sleep
    mocker.patch('bot.handlers.game.commands.time.sleep')
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidor_cmd(mock_update, mock_context)
    
    # Verify random.choice was called with players list
    assert mock_random_choice.call_count >= 1
    first_call_args = mock_random_choice.call_args_list[0][0]
    assert first_call_args[0] == sample_players


@pytest.mark.unit
def test_pidor_cmd_time_delays(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that time delays are called between messages."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_result_query]
    
    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        sample_players[0],
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
    ])
    
    # Mock time.sleep and capture calls
    mock_sleep = mocker.patch('bot.handlers.game.commands.time.sleep')
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidor_cmd(mock_update, mock_context)
    
    # Verify time.sleep was called 3 times with GAME_RESULT_TIME_DELAY (2 seconds)
    assert mock_sleep.call_count == 3
    for call in mock_sleep.call_args_list:
        assert call[0][0] == 2  # GAME_RESULT_TIME_DELAY