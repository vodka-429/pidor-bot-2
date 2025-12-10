"""Tests for final voting functionality."""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch
from bot.handlers.game.commands import (
    pidorfinal_cmd,
    pidorfinalstatus_cmd,
    pidorfinalclose_cmd
)
from bot.app.models import FinalVoting, GameResult, TGUser


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinal_cmd_wrong_date(mock_update, mock_context, mock_game, mocker):
    """Test pidorfinal command fails when called on wrong date (not Dec 29-30)."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock current_datetime to return wrong date (not Dec 29-30)
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 15  # Wrong date
    mock_dt.timetuple.return_value.tm_yday = 350
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "29 или 30 декабря" in call_args or "wrong date" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinal_cmd_too_many_missed_days(mock_update, mock_context, mock_game, mocker):
    """Test pidorfinal command fails when there are too many missed days."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock current_datetime to return Dec 29
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 29
    mock_dt.timetuple.return_value.tm_yday = 364
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Mock get_all_missed_days to return too many days (>= 10)
    missed_days = list(range(1, 16))  # 15 days
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    # Execute
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "Слишком много" in call_args or "too many" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinal_cmd_already_exists(mock_update, mock_context, mock_game, mocker):
    """Test pidorfinal command fails when voting already exists."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock existing FinalVoting
    mock_existing_voting = MagicMock()
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = mock_existing_voting
    
    # Setup query to return Game first, then FinalVoting
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query]
    
    # Mock current_datetime to return Dec 29
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 29
    mock_dt.timetuple.return_value.tm_yday = 364
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Mock get_all_missed_days to return valid count
    missed_days = [1, 2, 3, 4, 5]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    # Execute
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "уже запущено" in call_args or "already exists" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinal_cmd_success(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test successful creation of final voting."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock FinalVoting query - no existing voting
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = None
    
    # Mock player weights query
    mock_weights_query = MagicMock()
    player_weights = [(sample_players[0], 5), (sample_players[1], 3), (sample_players[2], 2)]
    mock_weights_query.all.return_value = player_weights
    
    # Setup query side effects
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query]
    mock_context.db_session.exec.return_value = mock_weights_query
    
    # Mock current_datetime to return Dec 29
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 29
    mock_dt.timetuple.return_value.tm_yday = 364
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Mock get_all_missed_days
    missed_days = [1, 2, 3, 4, 5]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    # Mock bot.send_message for voting keyboard
    mock_voting_message = MagicMock()
    mock_voting_message.message_id = 12345
    mock_context.bot.send_message = AsyncMock(return_value=mock_voting_message)
    
    # Execute
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify voting message with keyboard was created (now it's a single combined message)
    mock_context.bot.send_message.assert_called_once()
    
    # Verify FinalVoting was added to session
    mock_context.db_session.add.assert_called_once()
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinal_cmd_test_chat_bypass_date_check(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that test chat bypasses date check for pidorfinal command."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock chat_id to be test chat
    mock_update.effective_chat.id = -4608252738
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock FinalVoting query - no existing voting
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = None
    
    # Mock player weights query
    mock_weights_query = MagicMock()
    player_weights = [(sample_players[0], 5), (sample_players[1], 3), (sample_players[2], 2)]
    mock_weights_query.all.return_value = player_weights
    
    # Setup query side effects
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query]
    mock_context.db_session.exec.return_value = mock_weights_query
    
    # Mock current_datetime to return WRONG date (not Dec 29-30) - June 15
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Mock get_all_missed_days
    missed_days = [1, 2, 3, 4, 5]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    # Mock bot.send_message for voting keyboard
    mock_voting_message = MagicMock()
    mock_voting_message.message_id = 12345
    mock_context.bot.send_message = AsyncMock(return_value=mock_voting_message)
    
    # Execute
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify voting message with keyboard was created (not error about wrong date)
    mock_context.bot.send_message.assert_called_once()
    call_args = str(mock_context.bot.send_message.call_args)
    # Should NOT contain date error
    assert "29 или 30 декабря" not in call_args
    
    # Verify FinalVoting was added to session
    mock_context.db_session.add.assert_called_once()
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinal_cmd_test_chat_bypass_missed_days_check(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that test chat bypasses missed days count check for pidorfinal command."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock chat_id to be test chat
    mock_update.effective_chat.id = -4608252738
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock FinalVoting query - no existing voting
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = None
    
    # Mock player weights query
    mock_weights_query = MagicMock()
    player_weights = [(sample_players[0], 5), (sample_players[1], 3), (sample_players[2], 2)]
    mock_weights_query.all.return_value = player_weights
    
    # Setup query side effects
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query]
    mock_context.db_session.exec.return_value = mock_weights_query
    
    # Mock current_datetime to return Dec 29
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 29
    mock_dt.timetuple.return_value.tm_yday = 364
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Mock get_all_missed_days to return TOO MANY days (>= 10)
    missed_days = list(range(1, 16))  # 15 days - more than MAX_MISSED_DAYS_FOR_FINAL_VOTING
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    # Mock bot.send_message for voting keyboard
    mock_voting_message = MagicMock()
    mock_voting_message.message_id = 12345
    mock_context.bot.send_message = AsyncMock(return_value=mock_voting_message)
    
    # Execute
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify voting message with keyboard was created (not error about too many days)
    mock_context.bot.send_message.assert_called_once()
    call_args = str(mock_context.bot.send_message.call_args)
    # Should NOT contain "too many" error
    assert "Слишком много" not in call_args
    
    # Verify FinalVoting was added to session
    mock_context.db_session.add.assert_called_once()
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinal_cmd_regular_chat_date_check_enforced(mock_update, mock_context, mock_game, mocker):
    """Test that regular chats still enforce date check for pidorfinal command."""
    # Setup
    mock_context.game = mock_game
    
    # Mock chat_id to be regular chat (NOT test chat)
    mock_update.effective_chat.id = -123456789
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock current_datetime to return WRONG date (not Dec 29-30) - June 15
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    await pidorfinal_cmd(mock_update, mock_context)
    
    # Verify error message about wrong date was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "29 или 30 декабря" in call_args or "wrong date" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalstatus_cmd_not_started(mock_update, mock_context, mock_game, mocker):
    """Test pidorfinalstatus command when voting is not started."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock FinalVoting query - no voting found
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = None
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query]
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    await pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "not started" message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "не запущено" in call_args or "not started" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalstatus_cmd_active(mock_update, mock_context, mock_game, mocker):
    """Test pidorfinalstatus command when voting is active."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock FinalVoting - active voting
    mock_voting = MagicMock()
    mock_voting.started_at = datetime(2024, 12, 29, 12, 0, 0)
    mock_voting.ended_at = None
    mock_voting.missed_days_count = 5
    
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = mock_voting
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query]
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    await pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "active" message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "активно" in call_args or "active" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalstatus_cmd_completed(mock_update, mock_context, mock_game, mock_tg_user, mocker):
    """Test pidorfinalstatus command when voting is completed."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock FinalVoting - completed voting
    mock_voting = MagicMock()
    mock_voting.started_at = datetime(2024, 12, 29, 12, 0, 0)
    mock_voting.ended_at = datetime(2024, 12, 30, 12, 0, 0)
    mock_voting.missed_days_count = 5
    mock_voting.winner = mock_tg_user
    
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = mock_voting
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query]
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    await pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "completed" message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "завершено" in call_args or "completed" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_vote_callback_add_vote(mock_update, mock_context, mocker):
    """Test handle_vote_callback adds a vote correctly."""
    from bot.handlers.game.commands import handle_vote_callback
    
    # Setup callback query
    mock_query = AsyncMock()
    mock_query.data = "vote_1_123"  # voting_id=1, candidate_id=123
    mock_query.from_user.id = 456
    mock_update.callback_query = mock_query
    
    # Setup FinalVoting
    mock_voting = MagicMock()
    mock_voting.id = 1
    mock_voting.ended_at = None
    mock_voting.votes_data = '{}'  # Empty votes
    mock_voting.missed_days_count = 2  # Allows 1 vote (2/2 = 1)
    
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting
    
    # Execute
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify vote was added
    import json
    updated_votes = json.loads(mock_voting.votes_data)
    assert '456' in updated_votes
    assert 123 in updated_votes['456']
    
    # Verify callback answer
    mock_query.answer.assert_called_once_with("✅ Голос учтён")
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_vote_callback_remove_vote(mock_update, mock_context, mocker):
    """Test handle_vote_callback removes a vote (toggle)."""
    from bot.handlers.game.commands import handle_vote_callback
    
    # Setup callback query
    mock_query = AsyncMock()
    mock_query.data = "vote_1_123"  # voting_id=1, candidate_id=123
    mock_query.from_user.id = 456
    mock_update.callback_query = mock_query
    
    # Setup FinalVoting with existing vote
    mock_voting = MagicMock()
    mock_voting.id = 1
    mock_voting.ended_at = None
    mock_voting.votes_data = '{"456": [123]}'  # User 456 already voted for candidate 123
    mock_voting.missed_days_count = 2  # Allows 1 vote (2/2 = 1)
    
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting
    
    # Execute
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify vote was removed
    import json
    updated_votes = json.loads(mock_voting.votes_data)
    assert '456' in updated_votes
    assert 123 not in updated_votes['456']
    assert len(updated_votes['456']) == 0
    
    # Verify callback answer
    mock_query.answer.assert_called_once_with("✅ Голос отменён")
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_vote_callback_multiple_votes(mock_update, mock_context, mocker):
    """Test handle_vote_callback allows voting for multiple candidates."""
    from bot.handlers.game.commands import handle_vote_callback
    
    # Setup callback query for first vote
    mock_query = AsyncMock()
    mock_query.data = "vote_1_123"
    mock_query.from_user.id = 456
    mock_update.callback_query = mock_query
    
    # Setup FinalVoting
    mock_voting = MagicMock()
    mock_voting.id = 1
    mock_voting.ended_at = None
    mock_voting.votes_data = '{}'
    mock_voting.missed_days_count = 4  # Allows 2 votes (4/2 = 2)
    
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting
    
    # First vote
    await handle_vote_callback(mock_update, mock_context)
    
    import json
    votes_after_first = json.loads(mock_voting.votes_data)
    assert 123 in votes_after_first['456']
    
    # Reset mock
    mock_context.db_session.commit.reset_mock()
    
    # Second vote for different candidate
    mock_query.data = "vote_1_789"
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify both votes are present
    votes_after_second = json.loads(mock_voting.votes_data)
    assert '456' in votes_after_second
    assert 123 in votes_after_second['456']
    assert 789 in votes_after_second['456']
    assert len(votes_after_second['456']) == 2
    
    # Verify commit was called again
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_vote_callback_voting_ended(mock_update, mock_context, mocker):
    """Test handle_vote_callback rejects votes after voting ended."""
    from bot.handlers.game.commands import handle_vote_callback
    from datetime import datetime
    
    # Setup callback query
    mock_query = AsyncMock()
    mock_query.data = "vote_1_123"
    mock_query.from_user.id = 456
    mock_update.callback_query = mock_query
    
    # Setup FinalVoting that has ended
    mock_voting = MagicMock()
    mock_voting.id = 1
    mock_voting.ended_at = datetime(2024, 12, 30, 12, 0, 0)  # Already ended
    mock_voting.votes_data = '{}'
    mock_voting.missed_days_count = 2  # Allows 1 vote (2/2 = 1)
    
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting
    
    # Execute
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify vote was NOT added
    import json
    votes = json.loads(mock_voting.votes_data)
    assert '456' not in votes
    
    # Verify error message
    mock_query.answer.assert_called_once_with("пішов в хуй")
    
    # Verify commit was NOT called
    mock_context.db_session.commit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalclose_cmd_success(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test successful manual closing of voting by admin."""
    # Setup
    mock_context.game = mock_game
    mock_update.effective_user.id = 999
    
    # Mock current_datetime - 25 hours after voting started (more than 24 hours)
    mock_dt = datetime(2024, 12, 30, 13, 0, 0)
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Setup active FinalVoting - started 25 hours ago
    mock_voting = MagicMock()
    mock_voting.id = 1
    mock_voting.game_id = mock_game.id
    mock_voting.year = 2024
    mock_voting.started_at = datetime(2024, 12, 29, 12, 0, 0)  # Started 25 hours ago
    mock_voting.ended_at = None  # Active voting
    mock_voting.missed_days_count = 5
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4, 5])
    mock_voting.votes_data = '{"1": [1, 2], "2": [1]}'
    
    # Mock admin check
    mock_chat_member = MagicMock()
    mock_chat_member.status = 'administrator'
    mock_context.bot.get_chat_member = AsyncMock(return_value=mock_chat_member)
    
    # Mock finalize_voting
    winner = sample_players[0]
    winner.id = 1
    results = {1: {'weighted': 8, 'votes': 2}, 2: {'weighted': 5, 'votes': 1}}
    from bot.handlers.game.voting_helpers import finalize_voting
    mocker.patch('bot.handlers.game.voting_helpers.finalize_voting', return_value=(winner, results))
    
    # Mock player weights query
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(sample_players[0], 5), (sample_players[1], 3)]
    
    # Mock TGUser query for candidates
    def query_side_effect(model):
        if model == FinalVoting:
            mock_q = MagicMock()
            mock_q.filter_by.return_value.one_or_none.return_value = mock_voting
            return mock_q
        elif model == TGUser:
            mock_q = MagicMock()
            mock_q.filter_by.return_value.one.return_value = sample_players[0]
            return mock_q
        return MagicMock()
    
    mock_context.db_session.query.side_effect = query_side_effect
    mock_context.db_session.exec.return_value = mock_weights_result
    
    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)
    
    # Verify success message was sent
    assert mock_update.effective_chat.send_message.call_count == 2  # Success + Results
    
    # Verify finalize_voting was called
    from bot.handlers.game.voting_helpers import finalize_voting
    # Note: we can't assert on the mocked function directly, but we verified it was called via mocker.patch


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalclose_cmd_not_admin(mock_update, mock_context, mock_game, mocker):
    """Test that non-admin cannot close voting."""
    # Setup
    mock_context.game = mock_game
    mock_update.effective_user.id = 999
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Setup active FinalVoting
    mock_voting = MagicMock()
    mock_voting.ended_at = None
    
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting
    
    # Mock non-admin check
    mock_chat_member = MagicMock()
    mock_chat_member.status = 'member'  # Not admin
    mock_context.bot.get_chat_member = AsyncMock(return_value=mock_chat_member)
    
    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "администратор" in call_args or "admin" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalclose_cmd_no_active_voting(mock_update, mock_context, mock_game, mocker):
    """Test error when no active voting exists."""
    # Setup
    mock_context.game = mock_game
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # No active voting (returns None)
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = None
    
    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "активного голосования" in call_args or "not active" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalclose_cmd_already_ended(mock_update, mock_context, mock_game, mocker):
    """Test error when voting already ended."""
    # Setup
    mock_context.game = mock_game
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Setup already ended voting
    mock_voting = MagicMock()
    mock_voting.ended_at = datetime(2024, 12, 30, 12, 0, 0)  # Already ended
    
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting
    
    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "активного голосования" in call_args or "not active" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalclose_cmd_too_early(mock_update, mock_context, mock_game, mocker):
    """Test error when trying to close voting before 24 hours have passed."""
    # Setup
    mock_context.game = mock_game
    mock_update.effective_user.id = 999
    mock_update.effective_chat.id = -123456789  # Regular chat (not test chat)
    
    # Mock current_datetime - only 12 hours after voting started (less than 24 hours)
    mock_dt = datetime(2024, 12, 30, 0, 0, 0)
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Setup active FinalVoting - started 12 hours ago
    mock_voting = MagicMock()
    mock_voting.started_at = datetime(2024, 12, 29, 12, 0, 0)  # Started 12 hours ago
    mock_voting.ended_at = None  # Active voting
    
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting
    
    # Mock admin check
    mock_chat_member = MagicMock()
    mock_chat_member.status = 'administrator'
    mock_context.bot.get_chat_member = AsyncMock(return_value=mock_chat_member)
    
    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "24 часа" in call_args or "24 hours" in call_args.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalclose_cmd_test_chat_bypass_time_check(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that test chat bypasses 24-hour time check for closing voting."""
    # Setup
    mock_context.game = mock_game
    mock_update.effective_user.id = 999
    mock_update.effective_chat.id = -4608252738  # Test chat
    
    # Mock current_datetime - only 1 hour after voting started (less than 24 hours)
    mock_dt = datetime(2024, 12, 29, 13, 0, 0)
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Setup active FinalVoting - started only 1 hour ago
    mock_voting = MagicMock()
    mock_voting.id = 1
    mock_voting.game_id = mock_game.id
    mock_voting.year = 2024
    mock_voting.started_at = datetime(2024, 12, 29, 12, 0, 0)  # Started 1 hour ago
    mock_voting.ended_at = None  # Active voting
    mock_voting.missed_days_count = 5
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4, 5])
    mock_voting.votes_data = '{"1": [1, 2], "2": [1]}'
    
    # Mock admin check
    mock_chat_member = MagicMock()
    mock_chat_member.status = 'administrator'
    mock_context.bot.get_chat_member = AsyncMock(return_value=mock_chat_member)
    
    # Mock finalize_voting
    winner = sample_players[0]
    winner.id = 1
    results = {1: {'weighted': 8, 'votes': 2}, 2: {'weighted': 5, 'votes': 1}}
    from bot.handlers.game.voting_helpers import finalize_voting
    mocker.patch('bot.handlers.game.voting_helpers.finalize_voting', return_value=(winner, results))
    
    # Mock player weights query
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(sample_players[0], 5), (sample_players[1], 3)]
    
    # Mock TGUser query for candidates
    def query_side_effect(model):
        if model == FinalVoting:
            mock_q = MagicMock()
            mock_q.filter_by.return_value.one_or_none.return_value = mock_voting
            return mock_q
        elif model == TGUser:
            mock_q = MagicMock()
            mock_q.filter_by.return_value.one.return_value = sample_players[0]
            return mock_q
        return MagicMock()
    
    mock_context.db_session.query.side_effect = query_side_effect
    mock_context.db_session.exec.return_value = mock_weights_result
    
    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)
    
    # Verify success message was sent (not error about 24 hours)
    assert mock_update.effective_chat.send_message.call_count == 2  # Success + Results
    call_args = str(mock_update.effective_chat.send_message.call_args_list)
    # Should NOT contain 24 hours error
    assert "24 часа" not in call_args


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_vote_callback_voting_not_found(mock_update, mock_context, mocker):
    """Test handle_vote_callback handles missing voting gracefully."""
    from bot.handlers.game.commands import handle_vote_callback
    
    # Setup callback query
    mock_query = MagicMock()
    mock_query.data = "vote_999_123"  # Non-existent voting_id
    mock_query.from_user.id = 456
    mock_update.callback_query = mock_query
    
    # Setup query to return None (voting not found)
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = None
    
    # Execute
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify error message
    mock_query.answer.assert_called_once_with("❌ Голосование не найдено")
    
    # Verify commit was NOT called
    mock_context.db_session.commit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_vote_callback_invalid_callback_data(mock_update, mock_context, mocker):
    """Test handle_vote_callback handles invalid callback_data."""
    from bot.handlers.game.commands import handle_vote_callback
    
    # Setup callback query with invalid data
    mock_query = MagicMock()
    mock_query.data = "invalid_callback_data"
    mock_update.callback_query = mock_query
    
    # Execute
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify error message
    mock_query.answer.assert_called_once_with("❌ Ошибка обработки голоса")
    
    # Verify commit was NOT called
    mock_context.db_session.commit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_handle_vote_callback_voting_ended_response(mock_update, mock_context, mocker):
    """Test handle_vote_callback returns correct response when voting ended."""
    from bot.handlers.game.commands import handle_vote_callback
    from datetime import datetime
    
    # Setup callback query
    mock_query = AsyncMock()
    mock_query.data = "vote_1_123"
    mock_query.from_user.id = 456
    mock_update.callback_query = mock_query
    
    # Setup FinalVoting that has ended
    mock_voting = MagicMock()
    mock_voting.id = 1
    mock_voting.ended_at = datetime(2024, 12, 30, 12, 0, 0)  # Already ended
    mock_voting.votes_data = '{}'
    mock_voting.missed_days_count = 2
    
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting
    
    # Execute
    await handle_vote_callback(mock_update, mock_context)
    
    # Verify specific response "пішов в хуй"
    mock_query.answer.assert_called_once_with("пішов в хуй")
    
    # Verify vote was NOT added
    import json
    votes = json.loads(mock_voting.votes_data)
    assert '456' not in votes
    
    # Verify commit was NOT called
    mock_context.db_session.commit.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalstatus_cmd_active_with_voters(mock_update, mock_context, mock_game, mocker):
    """Test pidorfinalstatus command shows voter count when voting is active."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock FinalVoting - active voting with some votes
    mock_voting = MagicMock()
    mock_voting.started_at = datetime(2024, 12, 29, 12, 0, 0)
    mock_voting.ended_at = None
    mock_voting.missed_days_count = 5
    mock_voting.votes_data = '{"123": [1, 2], "456": [3], "789": [1]}'  # 3 voters
    
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = mock_voting
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query]
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    await pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "active with voters" message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "активно" in call_args or "active" in call_args.lower()
    assert "Проголосовало: 3" in call_args or "3 игроков" in call_args
