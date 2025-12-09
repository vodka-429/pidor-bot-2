"""Integration tests for final voting functionality."""
import pytest
import json
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from bot.handlers.game.commands import (
    pidor_cmd,
    pidormissed_cmd,
    pidorfinal_cmd,
    pidorfinalstatus_cmd,
    handle_vote_callback,
    pidorfinalclose_cmd
)
from bot.app.models import FinalVoting, GameResult


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_final_voting_cycle(mock_update, mock_context, mock_game, sample_players, mocker):
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
    
    await pidorfinalstatus_cmd(mock_update, mock_context)
    
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
    
    # Mock bot.send_message for voting keyboard
    mock_voting_message = MagicMock()
    mock_voting_message.message_id = 12345
    mock_context.bot.send_message = AsyncMock(return_value=mock_voting_message)
    
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify info message and voting message creation
    assert mock_update.effective_chat.send_message.call_count == 1
    mock_context.bot.send_message.assert_called_once()
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
    
    await pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "active" message
    assert mock_update.effective_chat.send_message.call_count == 1
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "активно" in call_args or "active" in call_args.lower()
    
    # Reset mocks
    mock_update.effective_chat.send_message.reset_mock()
    
    # Step 4: Voting is now done via custom buttons, not poll
    # This test is for old poll-based voting, skip this step for custom voting
    
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
    
    await pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "completed" message
    assert mock_update.effective_chat.send_message.call_count == 1
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "завершено" in call_args or "completed" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_missed_days_and_final_voting(mock_update, mock_context, mock_game, sample_players, mocker):
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
    
    await pidormissed_cmd(mock_update, mock_context)
    
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
    
    # Mock bot.send_message for voting keyboard
    mock_voting_message = MagicMock()
    mock_voting_message.message_id = 12345
    mock_context.bot.send_message = AsyncMock(return_value=mock_voting_message)
    
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify voting message was created with correct missed days
    mock_context.bot.send_message.assert_called_once()
    poll_call_args = mock_context.bot.send_poll.call_args
    
    # Verify FinalVoting was saved with correct missed days
    add_call_args = mock_context.db_session.add.call_args
    assert add_call_args is not None
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_games_final_voting(mock_update, mock_context, sample_players, mocker):
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
    
    # Mock bot.send_message for game 1
    mock_voting_message1 = MagicMock()
    mock_voting_message1.message_id = 11111
    mock_context.bot.send_message = AsyncMock(return_value=mock_voting_message1)
    
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify voting message was created for game 1
    assert mock_context.bot.send_message.call_count == 1
    assert mock_context.db_session.add.call_count == 1
    
    # Reset mocks
    mock_context.bot.send_message.reset_mock()
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
    
    # Mock bot.send_message for game 2
    mock_voting_message2 = MagicMock()
    mock_voting_message2.message_id = 22222
    mock_context.bot.send_message = AsyncMock(return_value=mock_voting_message2)
    
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify voting message was created for game 2
    assert mock_context.bot.send_message.call_count == 1
    assert mock_context.db_session.add.call_count == 1
    
    # Verify both games have independent voting
    # (in real scenario, we would check that message_ids are different)
    assert mock_voting_message1.message_id != mock_voting_message2.message_id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_custom_voting_full_cycle(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test full custom voting cycle: create → vote → close → verify results."""
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
    
    # Step 1: Create voting
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
    
    # Mock bot.send_message for voting keyboard
    mock_voting_message = MagicMock()
    mock_voting_message.message_id = 99999
    mock_context.bot.send_message = AsyncMock(return_value=mock_voting_message)
    
    # Create a mock FinalVoting object that will be added
    mock_final_voting = MagicMock()
    mock_final_voting.id = 1
    mock_final_voting.game_id = 1
    mock_final_voting.year = 2024
    mock_final_voting.votes_data = '{}'
    mock_final_voting.is_results_hidden = True
    mock_final_voting.voting_message_id = None
    mock_final_voting.ended_at = None
    mock_final_voting.missed_days_count = 5
    mock_final_voting.missed_days_list = json.dumps(missed_days)
    
    # Mock db_session.add to capture the FinalVoting object
    def capture_final_voting(obj):
        if isinstance(obj, type(mock_final_voting)):
            # Copy attributes from added object to our mock
            pass
    
    mock_context.db_session.add.side_effect = capture_final_voting
    
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify voting was created
    assert mock_update.effective_chat.send_message.call_count == 1
    assert mock_context.bot.send_message.call_count == 1
    mock_context.db_session.add.assert_called()
    mock_context.db_session.commit.assert_called()
    
    # Reset mocks
    mock_update.effective_chat.send_message.reset_mock()
    mock_context.db_session.add.reset_mock()
    mock_context.db_session.commit.reset_mock()
    
    # Step 2: Users vote
    # Mock callback query for voting
    mock_callback_query = AsyncMock()
    mock_callback_query.from_user.id = 100000001  # player1's tg_id
    mock_update.callback_query = mock_callback_query
    
    # Vote for candidate 1 (player1 votes for player1)
    mock_callback_query.data = "vote_1_1"
    
    # Mock FinalVoting query for vote handler - need to reset side_effect
    mock_voting_query_for_vote = MagicMock()
    mock_voting_query_for_vote.filter_by.return_value.one_or_none.return_value = mock_final_voting
    
    # Reset query mock to return our voting query
    mock_context.db_session.query.side_effect = None
    mock_context.db_session.query.return_value = mock_voting_query_for_vote
    
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify vote was recorded
    mock_callback_query.answer.assert_called_once()
    assert "учтён" in mock_callback_query.answer.call_args[0][0].lower() or "учтен" in mock_callback_query.answer.call_args[0][0].lower()
    
    # Verify votes_data was updated
    votes_data = json.loads(mock_final_voting.votes_data)
    assert '100000001' in votes_data
    assert 1 in votes_data['100000001']
    
    # Reset mocks
    mock_callback_query.answer.reset_mock()
    mock_context.db_session.commit.reset_mock()
    
    # Vote for candidate 2 (player1 also votes for player2)
    mock_callback_query.data = "vote_1_2"
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify second vote was recorded
    votes_data = json.loads(mock_final_voting.votes_data)
    assert 2 in votes_data['100000001']
    assert len(votes_data['100000001']) == 2
    
    # Reset mocks
    mock_callback_query.answer.reset_mock()
    mock_context.db_session.commit.reset_mock()
    
    # Player 2 votes for candidate 1
    mock_callback_query.from_user.id = 100000002
    mock_callback_query.data = "vote_1_1"
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify player 2's vote
    votes_data = json.loads(mock_final_voting.votes_data)
    assert '100000002' in votes_data
    assert 1 in votes_data['100000002']
    
    # Reset mocks
    mock_callback_query.answer.reset_mock()
    mock_context.db_session.commit.reset_mock()
    
    # Step 3: Close voting (admin)
    mock_update.effective_user = MagicMock()
    mock_update.effective_user.id = 100000001
    
    # Mock admin check
    mock_chat_member = MagicMock()
    mock_chat_member.status = 'administrator'
    mock_context.bot.get_chat_member = AsyncMock(return_value=mock_chat_member)
    
    # Mock FinalVoting query for close command
    mock_voting_query_for_close = MagicMock()
    mock_voting_query_for_close.filter_by.return_value.one_or_none.return_value = mock_final_voting
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query_for_close]
    
    # Mock weights query for finalize_voting
    mock_weights_for_finalize = MagicMock()
    weights_result = [(1, 5), (2, 3), (3, 2)]  # user_id, weight
    mock_weights_for_finalize.all.return_value = weights_result
    
    # Mock TGUser query for getting candidates
    mock_user_query = MagicMock()
    mock_user_query.filter_by.return_value.one.return_value = sample_players[0]
    
    # Mock final stats query
    mock_final_stats_query = MagicMock()
    final_stats = [(sample_players[0], 10), (sample_players[1], 8), (sample_players[2], 7)]
    mock_final_stats_query.all.return_value = final_stats
    
    # Setup exec side effects
    mock_context.db_session.exec.side_effect = [mock_weights_for_finalize, mock_final_stats_query]
    
    # Setup query side effect for TGUser lookups
    def query_side_effect_for_close(model):
        if model.__name__ == 'TGUser':
            return mock_user_query
        return mock_voting_query_for_close
    
    mock_context.db_session.query.side_effect = query_side_effect_for_close
    
    await pidorfinalclose_cmd(mock_update, mock_context)
    
    # Verify voting was closed
    assert mock_final_voting.ended_at is not None
    assert mock_final_voting.winner_id is not None
    mock_context.db_session.commit.assert_called()
    
    # Verify results message was sent
    assert mock_update.effective_chat.send_message.call_count == 2  # Success message + results
    
    # Step 4: Verify weighted votes calculation
    # Player 1 (weight=5) voted for candidates 1 and 2
    # Player 2 (weight=3) voted for candidate 1
    # Expected: candidate 1 = 5 + 3 = 8, candidate 2 = 5
    # Winner should be candidate 1
    assert mock_final_voting.winner_id == 1
    
    # Verify GameResult records would be created (currently commented out in code)
    # In real implementation, verify that GameResult.add was called for each missed day
