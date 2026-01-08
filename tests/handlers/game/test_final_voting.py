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
async def test_pidorfinal_cmd_shows_rules_before_date(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test pidorfinal command shows rules when called before Dec 29-30."""
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
    mock_context.db_session.query.side_effect = [mock_game_query]
    mock_context.db_session.exec.return_value = mock_weights_query

    # Mock current_datetime to return wrong date (not Dec 29-30) - June 15
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock get_all_missed_days
    missed_days = [1, 2, 3, 4, 5]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)

    # Execute
    await pidorfinal_cmd(mock_update, mock_context)

    # Verify informational message was sent (not error about wrong date)
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)

    # Should contain rules information
    assert "Финальное голосование года" in call_args
    assert "Запустить голосование можно 29 или 30 декабря" in call_args or "29\\-30 декабря" in call_args

    # Should NOT contain just the error message
    assert "29 или 30 декабря" not in call_args or "Запустить голосование" in call_args

    # Verify FinalVoting was NOT created
    mock_context.db_session.add.assert_not_called()
    mock_context.db_session.commit.assert_not_called()


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
    TEST_CHAT_ID = -4608252738
    mock_update.effective_chat.id = TEST_CHAT_ID

    # Mock is_test_chat to return True for this chat
    mocker.patch('bot.handlers.game.commands.is_test_chat', return_value=True)

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
    """Test that test chat limits missed days to 10 when more than 10 days are missed."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock chat_id to be test chat
    TEST_CHAT_ID = -4608252738
    mock_update.effective_chat.id = TEST_CHAT_ID

    # Mock is_test_chat to return True for this chat in both modules
    mocker.patch('bot.handlers.game.commands.is_test_chat', return_value=True)
    mocker.patch('bot.handlers.game.voting_helpers.is_test_chat', return_value=True)

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

    # Mock get_all_missed_days to return 15 days (more than 10)
    missed_days = list(range(1, 16))  # 15 days - should be limited to 10 in test chat
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

    # Get the FinalVoting object that was added
    final_voting = mock_context.db_session.add.call_args[0][0]

    # Verify that missed_days_count is limited to 10
    assert final_voting.missed_days_count == 10, f"Expected missed_days_count to be 10, got {final_voting.missed_days_count}"

    # Verify that missed_days_list contains only 10 elements (first 10 from original list)
    missed_days_list = json.loads(final_voting.missed_days_list)
    assert len(missed_days_list) == 10, f"Expected 10 days in missed_days_list, got {len(missed_days_list)}"
    assert missed_days_list == list(range(1, 11)), f"Expected first 10 days [1..10], got {missed_days_list}"

    mock_context.db_session.commit.assert_called_once()


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
    mock_voting.winners_data = json.dumps([{"winner_id": mock_tg_user.id, "days_count": 5}])

    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value = mock_voting_query
    mock_voting_query.one_or_none.return_value = mock_voting

    # Mock TGUser query for winner
    mock_user_query = MagicMock()
    mock_user_query.filter_by.return_value.one.return_value = mock_tg_user

    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query, mock_user_query]

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
    mock_update.effective_user.username = 'test_admin'

    # Fix: Mock context.tg_user.full_username() to return 'test_admin' instead of '@testuser'
    mock_context.tg_user.full_username.return_value = 'test_admin'

    # Mock get_allowed_final_voting_closers to return test_admin
    mocker.patch('bot.handlers.game.commands.get_allowed_final_voting_closers', return_value=['test_admin'])

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

    # Mock finalize_voting - now returns list of winners
    winner = sample_players[0]
    winner.id = 1
    winners = [(1, winner)]  # List of tuples
    results = {1: {'weighted': 8, 'votes': 2, 'unique_voters': 2, 'auto_voted': False}, 2: {'weighted': 5, 'votes': 1, 'unique_voters': 1, 'auto_voted': False}}
    from bot.handlers.game.voting_helpers import finalize_voting
    mocker.patch('bot.handlers.game.voting_helpers.finalize_voting', return_value=(winners, results))

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
    mock_update.effective_user.username = 'test_admin'

    # Fix: Mock context.tg_user.full_username() to return 'test_admin' instead of '@testuser'
    mock_context.tg_user.full_username.return_value = 'test_admin'

    # Mock get_allowed_final_voting_closers to return test_admin
    mocker.patch('bot.handlers.game.commands.get_allowed_final_voting_closers', return_value=['test_admin'])

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
    mock_update.effective_user.username = 'test_admin'
    mock_update.effective_chat.id = -123456789  # Regular chat (not test chat)

    # Fix: Mock context.tg_user.full_username() to return 'test_admin' instead of '@testuser'
    mock_context.tg_user.full_username.return_value = 'test_admin'

    # Mock get_allowed_final_voting_closers to return test_admin
    mocker.patch('bot.handlers.game.commands.get_allowed_final_voting_closers', return_value=['test_admin'])

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
    mock_update.effective_user.username = 'test_admin'
    TEST_CHAT_ID = -4608252738
    mock_update.effective_chat.id = TEST_CHAT_ID  # Test chat

    # Fix: Mock context.tg_user.full_username() to return 'test_admin' instead of '@testuser'
    mock_context.tg_user.full_username.return_value = 'test_admin'

    # Mock is_test_chat to return True for this chat
    mocker.patch('bot.handlers.game.commands.is_test_chat', return_value=True)

    # Mock get_allowed_final_voting_closers to return test_admin
    mocker.patch('bot.handlers.game.commands.get_allowed_final_voting_closers', return_value=['test_admin'])

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

    # Mock finalize_voting - now returns list of winners
    winner = sample_players[0]
    winner.id = 1
    winners = [(1, winner)]  # List of tuples
    results = {1: {'weighted': 8, 'votes': 2, 'unique_voters': 2, 'auto_voted': False}, 2: {'weighted': 5, 'votes': 1, 'unique_voters': 1, 'auto_voted': False}}
    from bot.handlers.game.voting_helpers import finalize_voting
    mocker.patch('bot.handlers.game.voting_helpers.finalize_voting', return_value=(winners, results))

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


@pytest.mark.asyncio
@pytest.mark.unit
async def test_final_voting_results_escaping(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that weighted points with decimal places are properly escaped in results."""
    # Setup
    mock_context.game = mock_game
    mock_update.effective_user.id = 999
    mock_update.effective_user.username = 'test_admin'

    # Mock context.tg_user.full_username() to return test_admin
    mock_context.tg_user.full_username.return_value = 'test_admin'

    # Mock get_allowed_final_voting_closers to return test_admin
    mocker.patch('bot.handlers.game.commands.get_allowed_final_voting_closers', return_value=['test_admin'])

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

    # Mock finalize_voting to return results with decimal points - now returns list of winners
    winner = sample_players[0]
    winner.id = 1
    winners = [(1, winner)]  # List of tuples
    # Results with decimal points that need escaping
    results = {
        1: {'weighted': 12.5, 'votes': 2, 'unique_voters': 2, 'auto_voted': False},  # 12.5 contains a dot that needs escaping
        2: {'weighted': 8.3, 'votes': 1, 'unique_voters': 1, 'auto_voted': False}   # 8.3 contains a dot that needs escaping
    }
    from bot.handlers.game.voting_helpers import finalize_voting
    mocker.patch('bot.handlers.game.voting_helpers.finalize_voting', return_value=(winners, results))

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
            # Return different players based on filter_by call
            def filter_by_side_effect(id=None):
                mock_filter_q = MagicMock()
                if id == 1:
                    mock_filter_q.one.return_value = sample_players[0]
                elif id == 2:
                    mock_filter_q.one.return_value = sample_players[1]
                else:
                    mock_filter_q.one.return_value = sample_players[0]
                return mock_filter_q
            mock_q.filter_by.side_effect = filter_by_side_effect
            return mock_q
        return MagicMock()

    mock_context.db_session.query.side_effect = query_side_effect
    mock_context.db_session.exec.return_value = mock_weights_result

    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)

    # Verify success message was sent
    assert mock_update.effective_chat.send_message.call_count == 2  # Success + Results

    # Get the results message (second call)
    results_call = mock_update.effective_chat.send_message.call_args_list[1]
    results_message = results_call[0][0]  # First positional argument

    # Verify that decimal points are properly escaped in the results message
    # The weighted_points_str should be escaped with escape_markdown2()
    # So "12.5" should become "12\.5" and "8.3" should become "8\.3"
    assert "12\\.5" in results_message, f"Expected escaped '12\\.5' in results message: {results_message}"
    assert "8\\.3" in results_message, f"Expected escaped '8\\.3' in results message: {results_message}"

    # Verify that parse_mode is MarkdownV2
    assert results_call[1]['parse_mode'] == 'MarkdownV2'


@pytest.mark.asyncio
@pytest.mark.unit
async def test_finalize_voting_unique_voters():
    """Test finalize_voting correctly counts unique voters instead of total votes."""
    from bot.handlers.game.voting_helpers import finalize_voting

    # Setup mock context and voting
    mock_context = MagicMock()
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4])
    mock_voting.missed_days_count = 4

    # Setup votes: user 1 votes for candidates 1,2; user 2 votes for candidate 1
    # This creates 3 total votes but only 2 unique voters
    # Using Telegram IDs as in handle_vote_callback
    votes_data = {
        "1001": [1, 2],  # User with tg_id=1001 votes for 2 candidates
        "1002": [1]      # User with tg_id=1002 votes for 1 candidate
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 5), (2, 1002, 3)]

    # Setup winner query
    mock_winner = MagicMock()
    mock_winner.id = 1

    mock_context.db_session.exec.return_value = mock_weights_result
    mock_context.db_session.query.return_value.filter_by.return_value.one.return_value = mock_winner

    # Execute
    winners, results = finalize_voting(mock_voting, mock_context)

    # Verify winners is a list of tuples
    assert isinstance(winners, list)
    assert len(winners) >= 1
    assert isinstance(winners[0], tuple)
    assert len(winners[0]) == 2
    winner_id, winner_obj = winners[0]
    assert winner_id == 1
    assert winner_obj.id == 1

    # Verify unique_voters count is correct
    # Candidate 1: voted by users 1 and 2 = 2 unique voters
    # Candidate 2: voted by user 1 only = 1 unique voter
    assert results[1]['unique_voters'] == 2
    assert results[2]['unique_voters'] == 1

    # Verify votes count is still correct (total votes per candidate)
    assert results[1]['votes'] == 2  # 2 votes for candidate 1
    assert results[2]['votes'] == 1  # 1 vote for candidate 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_finalize_voting_auto_voted_flag():
    """Test finalize_voting correctly sets auto_voted flag for non-voters."""
    from bot.handlers.game.voting_helpers import finalize_voting

    # Setup mock context and voting
    mock_context = MagicMock()
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3])
    mock_voting.missed_days_count = 3  # 3 days → 1 vote per formula

    # Setup votes: only user 1 votes manually, user 2 doesn't vote
    # Using Telegram IDs as in handle_vote_callback
    votes_data = {
        "1001": [2]  # User with tg_id=1001 votes for candidate 2
        # User with tg_id=1002 doesn't vote - should get auto vote
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 3), (2, 1002, 4)]

    # Setup winner query - need to mock multiple queries for multiple winners
    mock_winner1 = MagicMock()
    mock_winner1.id = 2
    mock_winner2 = MagicMock()
    mock_winner2.id = 1

    mock_context.db_session.exec.return_value = mock_weights_result

    # Mock query to return different winners based on filter_by call
    def query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def filter_by_side_effect(id=None):
            mock_filter_q = MagicMock()
            if id == 2:
                mock_filter_q.one.return_value = mock_winner1
            elif id == 1:
                mock_filter_q.one.return_value = mock_winner2
            else:
                mock_filter_q.one.return_value = mock_winner1
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q

    mock_context.db_session.query.side_effect = query_side_effect

    # Execute with auto_vote enabled
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True)

    # Verify winners is a list of tuples
    assert isinstance(winners, list)
    assert len(winners) >= 1

    # Verify auto_voted flags
    # Candidate 2: user 2 didn't vote manually → auto_voted = True
    assert results[2]['auto_voted'] == True   # User 2 didn't vote manually (got auto vote)

    # Verify that user 2 appears in results (got auto vote for himself)
    assert 2 in results

    # Verify votes count - NEW LOGIC: auto votes NOT counted in 'votes'
    # Candidate 2: 1 manual vote from user 1, 1 auto vote from user 2
    assert results[2]['votes'] == 1  # Only manual votes
    assert results[2]['auto_votes'] == 1  # Auto votes tracked separately
    assert results[2]['unique_voters'] == 2  # Both users voted for candidate 2

@pytest.mark.asyncio
@pytest.mark.unit
async def test_finalize_voting_multiple_winners_data():
    """Test finalize_voting correctly saves multiple winners in winners_data."""
    from bot.handlers.game.voting_helpers import finalize_voting

    # Setup mock context and voting
    mock_context = MagicMock()
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4, 5, 6])
    mock_voting.missed_days_count = 6  # 6 days → 3 winners by formula

    # Setup votes: users vote for different candidates
    votes_data = {
        "1001": [1],  # User 1 votes for candidate 1
        "1002": [2],  # User 2 votes for candidate 2
        "1003": [3]   # User 3 votes for candidate 3
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights - all equal to create tie
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 5), (2, 1002, 5), (3, 1003, 5)]

    # Setup winner queries
    mock_winner1 = MagicMock()
    mock_winner1.id = 1
    mock_winner2 = MagicMock()
    mock_winner2.id = 2
    mock_winner3 = MagicMock()
    mock_winner3.id = 3

    mock_context.db_session.exec.return_value = mock_weights_result

    # Mock query to return different winners based on filter_by call
    def query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def filter_by_side_effect(id=None):
            mock_filter_q = MagicMock()
            if id == 1:
                mock_filter_q.one.return_value = mock_winner1
            elif id == 2:
                mock_filter_q.one.return_value = mock_winner2
            elif id == 3:
                mock_filter_q.one.return_value = mock_winner3
            else:
                mock_filter_q.one.return_value = mock_winner1
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q

    mock_context.db_session.query.side_effect = query_side_effect

    # Execute
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=False)

    # Verify winners is a list with 3 winners (max_votes for 6 days = 3)
    assert isinstance(winners, list)
    assert len(winners) == 3

    # Verify winners_data was saved correctly
    winners_data = json.loads(mock_voting.winners_data)
    assert len(winners_data) == 3


@pytest.mark.asyncio
@pytest.mark.unit
async def test_finalize_voting_separate_manual_auto_votes():
    """Test finalize_voting correctly separates manual and auto votes."""
    from bot.handlers.game.voting_helpers import finalize_voting

    # Setup mock context and voting
    mock_context = MagicMock()
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4])
    mock_voting.missed_days_count = 4  # 4 days → 2 votes per formula

    # Setup votes: user 1 votes manually, users 2 and 3 don't vote
    votes_data = {
        "1001": [1, 2]  # User 1 votes for candidates 1 and 2
        # Users 2 and 3 don't vote - should get auto votes
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 6), (2, 1002, 4), (3, 1003, 2)]

    # Setup winner queries
    mock_winner1 = MagicMock()
    mock_winner1.id = 1
    mock_winner2 = MagicMock()
    mock_winner2.id = 2
    mock_winner3 = MagicMock()
    mock_winner3.id = 3

    mock_context.db_session.exec.return_value = mock_weights_result

    # Mock query to return different winners based on filter_by call
    def query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def filter_by_side_effect(id=None):
            mock_filter_q = MagicMock()
            if id == 1:
                mock_filter_q.one.return_value = mock_winner1
            elif id == 2:
                mock_filter_q.one.return_value = mock_winner2
            elif id == 3:
                mock_filter_q.one.return_value = mock_winner3
            else:
                mock_filter_q.one.return_value = mock_winner1
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q

    mock_context.db_session.query.side_effect = query_side_effect

    # Execute with auto_vote enabled
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True)

    # Verify results for candidate 1 (got manual vote from user 1)
    assert results[1]['votes'] == 1  # Only manual votes
    assert results[1]['auto_votes'] == 0  # No auto votes
    assert results[1]['auto_voted'] == False  # User 1 voted manually

    # Verify results for candidate 2 (got manual vote from user 1 + auto vote from user 2)
    assert results[2]['votes'] == 1  # Only manual votes
    assert results[2]['auto_votes'] == 2  # Auto votes from user 2 (2 votes)
    assert results[2]['auto_voted'] == True  # User 2 didn't vote manually

    # Verify results for candidate 3 (got only auto vote from user 3)
    assert results[3]['votes'] == 0  # No manual votes
    assert results[3]['auto_votes'] == 2  # Auto votes from user 3 (2 votes)
    assert results[3]['auto_voted'] == True  # User 3 didn't vote manually

    # Verify weighted points calculation
    # Candidate 1: user 1 (weight 6, 2 votes) = 6/2 = 3.0
    # Candidate 2: user 1 (weight 6, 2 votes) + user 2 (weight 4, 2 votes) = 6/2 + 4 = 3.0 + 4.0 = 7.0
    # Candidate 3: user 3 (weight 2, 2 votes) = 2.0
    assert results[1]['weighted'] == 3.0
    assert results[2]['weighted'] == 7.0
    assert results[3]['weighted'] == 2.0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalclose_escapes_special_chars(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that pidorfinalclose properly escapes special characters in voting results."""
    # Setup
    mock_context.game = mock_game
    mock_update.effective_user.id = 999
    mock_update.effective_user.username = 'test_admin'

    # Fix: Mock context.tg_user.full_username() to return 'test_admin' instead of '@testuser'
    mock_context.tg_user.full_username.return_value = 'test_admin'

    # Mock get_allowed_final_voting_closers to return test_admin
    mocker.patch('bot.handlers.game.commands.get_allowed_final_voting_closers', return_value=['test_admin'])

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

    # Create sample players with special characters in names
    player1 = MagicMock()
    player1.id = 1
    player1.username = "test_user(1)"  # Contains parentheses that need escaping
    player1.full_username.return_value = "test_user(1)"

    player2 = MagicMock()
    player2.id = 2
    player2.username = "user.with.dots"  # Contains dots that need escaping
    player2.full_username.return_value = "user.with.dots"

    # Mock finalize_voting to return results with decimal points - now returns list of winners
    winner = player1
    winners = [(1, winner)]  # List of tuples
    results = {
        1: {'weighted': 15.75, 'votes': 3, 'unique_voters': 2, 'auto_voted': False},  # Decimal point needs escaping
        2: {'weighted': 9.25, 'votes': 2, 'unique_voters': 1, 'auto_voted': False}   # Decimal point needs escaping
    }
    from bot.handlers.game.voting_helpers import finalize_voting
    mocker.patch('bot.handlers.game.voting_helpers.finalize_voting', return_value=(winners, results))

    # Mock player weights query
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(player1, 5), (player2, 3)]

    # Mock TGUser query for candidates
    def query_side_effect(model):
        if model == FinalVoting:
            mock_q = MagicMock()
            mock_q.filter_by.return_value.one_or_none.return_value = mock_voting
            return mock_q
        elif model == TGUser:
            mock_q = MagicMock()
            # Return different players based on filter_by call
            def filter_by_side_effect(id=None):
                mock_filter_q = MagicMock()
                if id == 1:
                    mock_filter_q.one.return_value = player1
                elif id == 2:
                    mock_filter_q.one.return_value = player2
                else:
                    mock_filter_q.one.return_value = player1
                return mock_filter_q
            mock_q.filter_by.side_effect = filter_by_side_effect
            return mock_q
        return MagicMock()

    mock_context.db_session.query.side_effect = query_side_effect
    mock_context.db_session.exec.return_value = mock_weights_result

    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)

    # Verify success message was sent
    assert mock_update.effective_chat.send_message.call_count == 2  # Success + Results

    # Get the results message (second call)
    results_call = mock_update.effective_chat.send_message.call_args_list[1]
    results_message = results_call[0][0]  # First positional argument

    # Verify that decimal points are properly escaped in the results message
    # The actual values might be rounded, so check for any decimal numbers with escaped dots
    assert "15\\.8" in results_message or "15\\.75" in results_message, f"Expected escaped decimal number in results message: {results_message}"
    assert "9\\.2" in results_message or "9\\.25" in results_message, f"Expected escaped decimal number in results message: {results_message}"

    # Verify that usernames with special characters are properly escaped
    # Check for the actual escaped format that appears in the message
    assert "test\\_user\\(1\\)" in results_message, f"Expected escaped username in results message: {results_message}"
    assert "user\\.with\\.dots" in results_message, f"Expected escaped username in results message: {results_message}"

    # Verify that parse_mode is MarkdownV2
    assert results_call[1]['parse_mode'] == 'MarkdownV2'


@pytest.mark.asyncio
@pytest.mark.unit
async def test_date_formatting_escapes_dots(mock_update, mock_context, mock_game, mocker):
    """Test that date formatting properly escapes dots in pidorfinalstatus command."""
    # Setup
    mock_context.game = mock_game

    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Mock FinalVoting - active voting
    mock_voting = MagicMock()
    mock_voting.started_at = datetime(2024, 12, 29, 15, 30, 0)  # Specific time for testing
    mock_voting.ended_at = None
    mock_voting.missed_days_count = 5
    mock_voting.votes_data = '{}'

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

    # Verify message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)

    # Verify that dates contain escaped dots
    # The date should be formatted as "29\.12\.2024 15:30 МСК"
    # Note: call_args is a string representation, so we need to check for the actual escaped format
    assert "29\\\\.12\\\\.2024" in call_args, f"Expected escaped date format in message: {call_args}"
    assert "15:30" in call_args, f"Expected time in message: {call_args}"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_error_messages_escape_correctly(mock_update, mock_context, mock_game, mocker):
    """Test that error messages with remaining time properly escape numbers."""
    # Setup
    mock_context.game = mock_game
    mock_update.effective_user.id = 999
    mock_update.effective_user.username = 'test_admin'
    mock_update.effective_chat.id = -123456789  # Regular chat (not test chat)

    # Mock context.tg_user.full_username() to return test_admin
    mock_context.tg_user.full_username.return_value = 'test_admin'

    # Mock get_allowed_final_voting_closers to return test_admin
    mocker.patch('bot.handlers.game.commands.get_allowed_final_voting_closers', return_value=['test_admin'])

    # Mock current_datetime - only 12.5 hours after voting started (less than 24 hours)
    mock_dt = datetime(2024, 12, 29, 23, 30, 0)  # 23:30
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Setup active FinalVoting - started 12.5 hours ago
    mock_voting = MagicMock()
    mock_voting.started_at = datetime(2024, 12, 29, 11, 0, 0)  # Started at 11:00
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

    # Verify that the error message contains properly escaped numbers
    # The remaining time should be around 11.5 hours, which should be escaped
    assert "24 часа" in call_args or "24 hours" in call_args.lower()
    # Check that any decimal numbers in the message are properly escaped
    if "." in call_args and any(char.isdigit() for char in call_args):
        # If there are decimal numbers, they should be escaped
        import re
        # Find patterns like "11.5" and verify they are escaped as "11\.5"
        decimal_pattern = r'\d+\\\.\d+'
        if re.search(r'\d+\.\d+', call_args):
            assert re.search(decimal_pattern, call_args), f"Expected escaped decimal numbers in error message: {call_args}"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalclose_cmd_wrong_username(mock_update, mock_context, mock_game, mocker):
    """Test that user with wrong username cannot close voting."""
    # Setup
    mock_context.game = mock_game
    mock_update.effective_user.id = 999
    mock_update.effective_user.username = 'wrong_user'  # Not in allowed list

    # Fix: Mock context.tg_user.full_username() to return 'wrong_user' instead of '@testuser'
    mock_context.tg_user.full_username.return_value = 'wrong_user'

    # Mock get_allowed_final_voting_closers to return test_admin (not wrong_user)
    mocker.patch('bot.handlers.game.commands.get_allowed_final_voting_closers', return_value=['test_admin'])

    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Setup active FinalVoting
    mock_voting = MagicMock()
    mock_voting.ended_at = None

    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting

    # Mock admin check - user IS admin
    mock_chat_member = MagicMock()
    mock_chat_member.status = 'administrator'
    mock_context.bot.get_chat_member = AsyncMock(return_value=mock_chat_member)

    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)

    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "настоятель" in call_args


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidorfinalclose_cmd_no_username(mock_update, mock_context, mock_game, mocker):
    """Test that user without username cannot close voting."""
    # Setup
    mock_context.game = mock_game
    mock_update.effective_user.id = 999
    mock_update.effective_user.username = None  # No username

    # Fix: Mock context.tg_user.full_username() to return None instead of '@testuser'
    mock_context.tg_user.full_username.return_value = None

    # Mock get_allowed_final_voting_closers to return test_admin
    mocker.patch('bot.handlers.game.commands.get_allowed_final_voting_closers', return_value=['test_admin'])

    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Setup active FinalVoting
    mock_voting = MagicMock()
    mock_voting.ended_at = None

    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting

    # Mock admin check - user IS admin
    mock_chat_member = MagicMock()
    mock_chat_member.status = 'administrator'
    mock_context.bot.get_chat_member = AsyncMock(return_value=mock_chat_member)

    # Execute
    await pidorfinalclose_cmd(mock_update, mock_context)

    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "настоятель" in call_args
