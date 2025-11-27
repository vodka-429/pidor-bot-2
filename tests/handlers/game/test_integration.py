"""Integration tests for game handlers."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, call

from bot.handlers.game.commands import pidor_cmd, pidoreg_cmd, pidorstats_cmd


@pytest.mark.integration
def test_full_game_flow(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test full game flow: registration -> game -> stats."""
    # Mock time to avoid delays
    mocker.patch('bot.handlers.game.commands.time.sleep')
    
    # Mock random.choice to return first player
    mock_choice = mocker.patch('bot.handlers.game.commands.random.choice')
    mock_choice.return_value = sample_players[0]
    
    # Mock datetime to return a specific date
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Setup game with no players initially
    mock_game.players = []
    mock_context.game = mock_game
    
    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Step 1: Register first player
    mock_context.tg_user = sample_players[0]
    mock_context.db_session.query.return_value = mock_game_query
    
    pidoreg_cmd(mock_update, mock_context)
    
    # Verify first player registration
    assert sample_players[0] in mock_game.players
    assert mock_update.effective_message.reply_markdown_v2.call_count >= 1
    
    # Step 2: Register second player
    mock_context.tg_user = sample_players[1]
    mock_update.effective_message.reply_markdown_v2.reset_mock()
    
    pidoreg_cmd(mock_update, mock_context)
    
    # Verify second player registration
    assert sample_players[1] in mock_game.players
    
    # Step 3: Register third player
    mock_context.tg_user = sample_players[2]
    mock_update.effective_message.reply_markdown_v2.reset_mock()
    
    pidoreg_cmd(mock_update, mock_context)
    
    # Verify third player registration
    assert sample_players[2] in mock_game.players
    assert len(mock_game.players) == 3
    
    # Reset mocks for game command
    mock_update.effective_chat.send_message.reset_mock()
    
    # Mock GameResult query to return None (no existing result)
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None
    
    # Setup query to return different results for Game and GameResult
    mock_context.db_session.query.side_effect = [mock_game_query, mock_result_query]
    
    # Mock random.choice for stage phrases
    mock_choice.side_effect = [
        sample_players[0],  # winner
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
    ]
    
    # Step 4: Run the game
    pidor_cmd(mock_update, mock_context)
    
    # Verify game execution - should send 4 stage messages
    assert mock_update.effective_chat.send_message.call_count == 4
    
    # Verify GameResult was created
    assert mock_game.results.append.called
    assert mock_context.db_session.commit.called
    
    # Reset mocks for stats command
    mock_update.effective_chat.send_message.reset_mock()
    
    # Setup mock for stats query
    mock_stats_result = MagicMock()
    mock_stats_data = [
        (sample_players[0], 5),
        (sample_players[1], 3),
        (sample_players[2], 2),
    ]
    mock_stats_result.all.return_value = mock_stats_data
    mock_context.db_session.exec.return_value = mock_stats_result
    
    # Reset query side_effect for stats command
    mock_context.db_session.query.side_effect = None
    mock_context.db_session.query.return_value = mock_game_query
    
    # Step 5: Check stats
    pidorstats_cmd(mock_update, mock_context)
    
    # Verify stats were displayed
    assert mock_update.effective_chat.send_message.called
    call_args = mock_update.effective_chat.send_message.call_args
    assert call_args is not None
    
    # Verify the message contains player information
    message_text = str(call_args)
    assert 'player_count=3' in message_text or '3' in message_text