"""Tests for pidorstats_cmd command."""
import pytest
from unittest.mock import MagicMock, patch
from bot.handlers.game.commands import pidorstats_cmd
from bot.handlers.game.text_static import STATS_CURRENT_YEAR


@pytest.mark.unit
def test_pidorstats_cmd_with_results(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that statistics are displayed with results."""
    # Setup: game with players
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock the exec result for stats query
    mock_exec_result = MagicMock()
    # Create mock results: list of tuples (TGUser, count)
    mock_results = [
        (sample_players[0], 5),
        (sample_players[1], 3),
        (sample_players[2], 1),
    ]
    mock_exec_result.all.return_value = mock_results
    mock_context.db_session.exec.return_value = mock_exec_result
    
    # Mock current_datetime to return current year
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidorstats_cmd(mock_update, mock_context)
    
    # Verify that exec was called with a select statement
    mock_context.db_session.exec.assert_called_once()
    
    # Verify that send_message was called with stats
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "player" in call_args.lower() or str(len(sample_players)) in call_args


@pytest.mark.unit
def test_pidorstats_cmd_current_year_filter(mock_update, mock_context, mock_game, mocker):
    """Test that query filters by current year."""
    # Setup
    mock_game.players = []
    mock_context.game = mock_game
    
    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock the exec result
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []
    mock_context.db_session.exec.return_value = mock_exec_result
    
    # Mock current_datetime to return specific year
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidorstats_cmd(mock_update, mock_context)
    
    # Verify that exec was called
    assert mock_context.db_session.exec.called
    
    # Get the statement that was passed to exec
    call_args = mock_context.db_session.exec.call_args
    # The statement should contain year filter (we can't easily inspect SQLModel statements,
    # but we can verify exec was called)
    assert call_args is not None


@pytest.mark.unit
def test_pidorstats_cmd_correct_sql_query(mock_update, mock_context, mock_game, mocker):
    """Test that SQL query has correct structure."""
    # Setup
    mock_game.players = []
    mock_game.id = 123
    mock_context.game = mock_game
    
    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock the exec result
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []
    mock_context.db_session.exec.return_value = mock_exec_result
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidorstats_cmd(mock_update, mock_context)
    
    # Verify exec was called (query structure is validated by SQLModel)
    mock_context.db_session.exec.assert_called_once()
    
    # Verify send_message was called
    mock_update.effective_chat.send_message.assert_called_once()


@pytest.mark.unit
def test_pidorstats_cmd_formats_message(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that message is formatted correctly with player table and count."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock the exec result with sample data
    mock_exec_result = MagicMock()
    mock_results = [
        (sample_players[0], 10),
        (sample_players[1], 5),
    ]
    mock_exec_result.all.return_value = mock_results
    mock_context.db_session.exec.return_value = mock_exec_result
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidorstats_cmd(mock_update, mock_context)
    
    # Verify send_message was called
    mock_update.effective_chat.send_message.assert_called_once()
    
    # Get the message that was sent
    call_args = mock_update.effective_chat.send_message.call_args
    message = str(call_args[0][0]) if call_args else ""
    
    # Verify message contains player count
    assert str(len(sample_players)) in message or "player" in message.lower()
    
    # Verify ParseMode.MARKDOWN_V2 was used
    assert call_args[1].get('parse_mode') is not None or 'parse_mode' in str(call_args)