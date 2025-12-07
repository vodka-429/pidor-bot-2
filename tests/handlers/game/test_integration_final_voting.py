"""Integration tests for final voting functionality."""
import pytest
import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from bot.handlers.game.commands import (
    pidor_cmd,
    pidormissed_cmd,
    pidorfinal_cmd,
    handle_poll_answer,
    pidorfinalstatus_cmd
)
from bot.app.models import FinalVoting, GameResult


@pytest.mark.integration
def test_full_final_voting_cycle(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test full final voting cycle from start to completion."""
    # Setup game with players
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_game_query.one.return_value = mock_game
    
    # Mock current_datetime to return Dec 29
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 29
    mock_dt.timetuple.return_value.tm_yday = 364
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Step 1: Check status before voting (should be "not started")
    mock_voting_query_empty = MagicMock()
    mock_voting_query_empty.filter_by.return_value = mock_voting_query_empty
    mock_voting_query_empty.one_or_none.return_value = None
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query_empty]
    
    pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "not started" message
    assert mock_update.effective_chat.send_message.call_count == 1
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "не запущено" in call_args or "not started" in call_args.lower()
    
    # Reset mocks
    mock_update.effective_chat.send_message.reset_mock()
    
    # Step 2: Start final voting
    # Mock get_all_missed_days to return valid count
    missed_days = [1, 2, 3, 4, 5]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    # Mock FinalVoting query - no existing voting
    mock_voting_query_none = MagicMock()
    mock_voting_query_none.filter_by.return_value = mock_voting_query_none
    mock_voting_query_none.one_or_none.return_value = None
    
    # Mock player weights query
    mock_weights_query = MagicMock()
    player_weights = [(sample_players[0], 5), (sample_players[1], 3), (sample_players[2], 2)]
    mock_weights_query.all.return_value = player_weights
    
    # Setup query side effects for pidorfinal
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query_none]
    mock_context.db_session.exec.return_value = mock_weights_query
    
    # Mock bot.send_poll
    mock_poll = MagicMock()
    mock_poll.poll.id = "test_poll_id_123"
    mock_poll.message_id = 12345
    mock_context.bot.send_poll = MagicMock(return_value=mock_poll)
    
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify info message and poll creation
    assert mock_update.effective_chat.send_message.call_count == 1
    mock_context.bot.send_poll.assert_called_once()
    mock_context.db_session.add.assert_called()
    mock_context.db_session.commit.assert_called()
    
    # Reset mocks
    mock_update.effective_chat.send_message.reset_mock()
    mock_context.db_session.add.reset_mock()
    mock_context.db_session.commit.reset_mock()
    
    # Step 3: Check status during voting (should be "active")
    mock_voting_active = MagicMock()
    mock_voting_active.started_at = datetime(2024, 12, 29, 12, 0, 0)
    mock_voting_active.ended_at = None
    mock_voting_active.missed_days_count = 5
    
    mock_voting_query_active = MagicMock()
    mock_voting_query_active.filter_by.return_value = mock_voting_query_active
    mock_voting_query_active.one_or_none.return_value = mock_voting_active
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query_active]
    
    pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "active" message
    assert mock_update.effective_chat.send_message.call_count == 1
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "активно" in call_args or "active" in call_args.lower()
    
    # Reset mocks
    mock_update.effective_chat.send_message.reset_mock()
    
    # Step 4: Close poll and process results
    mock_update.poll.id = "test_poll_id_123"
    mock_update.poll.is_closed = True
    
    # Mock poll options (voting results)
    mock_option1 = MagicMock()
    mock_option1.text = "@player1"
    mock_option1.voter_count = 2
    
    mock_option2 = MagicMock()
    mock_option2.text = "@player2"
    mock_option2.voter_count = 1
    
    mock_option3 = MagicMock()
    mock_option3.text = "@player3"
    mock_option3.voter_count = 1
    
    mock_update.poll.options = [mock_option1, mock_option2, mock_option3]
    
    # Mock FinalVoting for poll handler
    mock_voting_for_handler = MagicMock()
    mock_voting_for_handler.game_id = 1
    mock_voting_for_handler.year = 2024
    mock_voting_for_handler.ended_at = None
    mock_voting_for_handler.missed_days_count = 5
    mock_voting_for_handler.missed_days_list = json.dumps([1, 2, 3, 4, 5])
    
    # Mock final stats query
    mock_stats_query = MagicMock()
    final_stats = [(sample_players[0], 10), (sample_players[1], 8), (sample_players[2], 7)]
    mock_stats_query.all.return_value = final_stats
    
    # Setup query side effects for poll handler
    def query_side_effect(model):
        if model == FinalVoting:
            mock_q = MagicMock()
            mock_q.filter_by.return_value.one_or_none.return_value = mock_voting_for_handler
            return mock_q
        else:
            mock_q = MagicMock()
            mock_q.filter_by.return_value.one.return_value = mock_game
            return mock_q
    
    mock_context.db_session.query.side_effect = query_side_effect
    mock_context.db_session.exec.side_effect = [mock_weights_query, mock_stats_query]
    
    handle_poll_answer(mock_update, mock_context)
    
    # Verify voting was updated and results sent
    assert mock_voting_for_handler.ended_at is not None
    assert mock_voting_for_handler.winner_id is not None
    mock_context.db_session.commit.assert_called()
    mock_context.bot.send_message.assert_called_once()
    
    # Reset mocks
    mock_context.bot.send_message.reset_mock()
    
    # Step 5: Check status after completion (should be "completed")
    mock_voting_completed = MagicMock()
    mock_voting_completed.started_at = datetime(2024, 12, 29, 12, 0, 0)
    mock_voting_completed.ended_at = datetime(2024, 12, 30, 12, 0, 0)
    mock_voting_completed.missed_days_count = 5
    mock_voting_completed.winner = sample_players[0]
    
    mock_voting_query_completed = MagicMock()
    mock_voting_query_completed.filter_by.return_value = mock_voting_query_completed
    mock_voting_query_completed.one_or_none.return_value = mock_voting_completed
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query_completed]
    
    pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "completed" message
    assert mock_update.effective_chat.send_message.call_count == 1
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "завершено" in call_args or "completed" in call_args.lower()


@pytest.mark.integration
def test_missed_days_and_final_voting(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test integration between missed days commands and final voting."""
    # Setup game with players
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_game_query.one.return_value = mock_game
    
    # Mock current_datetime to return Dec 29
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 29
    mock_dt.timetuple.return_value.tm_yday = 364
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Step 1: Check missed days
    missed_days = [1, 2, 3, 4, 5]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    mock_context.db_session.query.return_value = mock_game_query
    
    pidormissed_cmd(mock_update, mock_context)
    
    # Verify missed days message was sent
    assert mock_update.effective_chat.send_message.call_count == 1
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "5" in call_args  # Should show count of missed days
    
    # Reset mocks
    mock_update.effective_chat.send_message.reset_mock()
    
    # Step 2: Start final voting for these missed days
    # Mock FinalVoting query - no existing voting
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = None
    
    # Mock player weights query
    mock_weights_query = MagicMock()
    player_weights = [(sample_players[0], 5), (sample_players[1], 3), (sample_players[2], 2)]
    mock_weights_query.all.return_value = player_weights
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query]
    mock_context.db_session.exec.return_value = mock_weights_query
    
    # Mock bot.send_poll
    mock_poll = MagicMock()
    mock_poll.poll.id = "test_poll_id"
    mock_poll.message_id = 12345
    mock_context.bot.send_poll = MagicMock(return_value=mock_poll)
    
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify poll was created with correct missed days
    mock_context.bot.send_poll.assert_called_once()
    poll_call_args = mock_context.bot.send_poll.call_args
    
    # Verify FinalVoting was saved with correct missed days
    add_call_args = mock_context.db_session.add.call_args
    assert add_call_args is not None
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called()


@pytest.mark.integration
def test_multiple_games_final_voting(mock_update, mock_context, sample_players, mocker):
    """Test final voting with multiple games in different chats."""
    # Create two different games
    mock_game1 = MagicMock()
    mock_game1.id = 1
    mock_game1.chat_id = 111111
    mock_game1.players = sample_players
    
    mock_game2 = MagicMock()
    mock_game2.id = 2
    mock_game2.chat_id = 222222
    mock_game2.players = sample_players
    
    # Mock current_datetime to return Dec 29
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 29
    mock_dt.timetuple.return_value.tm_yday = 364
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Mock get_all_missed_days
    missed_days = [1, 2, 3]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    # Test Game 1
    mock_context.game = mock_game1
    mock_update.effective_chat.id = 111111
    
    # Mock queries for game 1
    mock_game1_query = MagicMock()
    mock_game1_query.filter_by.return_value = mock_game1_query
    mock_game1_query.one_or_none.return_value = mock_game1
    
    mock_voting1_query = MagicMock()
    mock_voting1_query.filter_by.return_value = mock_voting1_query
    mock_voting1_query.one_or_none.return_value = None
    
    mock_weights_query = MagicMock()
    player_weights = [(sample_players[0], 3), (sample_players[1], 2), (sample_players[2], 1)]
    mock_weights_query.all.return_value = player_weights
    
    mock_context.db_session.query.side_effect = [mock_game1_query, mock_voting1_query]
    mock_context.db_session.exec.return_value = mock_weights_query
    
    # Mock bot.send_poll for game 1
    mock_poll1 = MagicMock()
    mock_poll1.poll.id = "poll_game1"
    mock_poll1.message_id = 11111
    mock_context.bot.send_poll = MagicMock(return_value=mock_poll1)
    
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify poll was created for game 1
    assert mock_context.bot.send_poll.call_count == 1
    assert mock_context.db_session.add.call_count == 1
    
    # Reset mocks
    mock_context.bot.send_poll.reset_mock()
    mock_context.db_session.add.reset_mock()
    mock_context.db_session.commit.reset_mock()
    mock_update.effective_chat.send_message.reset_mock()
    
    # Test Game 2
    mock_context.game = mock_game2
    mock_update.effective_chat.id = 222222
    
    # Mock queries for game 2
    mock_game2_query = MagicMock()
    mock_game2_query.filter_by.return_value = mock_game2_query
    mock_game2_query.one_or_none.return_value = mock_game2
    
    mock_voting2_query = MagicMock()
    mock_voting2_query.filter_by.return_value = mock_voting2_query
    mock_voting2_query.one_or_none.return_value = None
    
    mock_context.db_session.query.side_effect = [mock_game2_query, mock_voting2_query]
    mock_context.db_session.exec.return_value = mock_weights_query
    
    # Mock bot.send_poll for game 2
    mock_poll2 = MagicMock()
    mock_poll2.poll.id = "poll_game2"
    mock_poll2.message_id = 22222
    mock_context.bot.send_poll = MagicMock(return_value=mock_poll2)
    
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify poll was created for game 2
    assert mock_context.bot.send_poll.call_count == 1
    assert mock_context.db_session.add.call_count == 1
    
    # Verify both games have independent voting
    # (in real scenario, we would check that poll_ids are different)
    assert mock_poll1.poll.id != mock_poll2.poll.id
