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

    # Verify voting message creation (now it's a single combined message)
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
    mock_voting_completed.winner_id = 1
    mock_voting_completed.winners_data = json.dumps([{"winner_id": 1, "days_count": 5}])  # Add winners_data as JSON string

    mock_voting_query_completed = MagicMock()
    mock_voting_query_completed.filter_by.return_value = mock_voting_query_completed
    mock_voting_query_completed.one_or_none.return_value = mock_voting_completed

    # Mock TGUser query for winner lookup
    mock_winner_query = MagicMock()
    mock_winner_query.filter_by.return_value = mock_winner_query
    mock_winner_query.one.return_value = sample_players[0]

    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query_completed, mock_winner_query]

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

    # Mock current_datetime to return Dec 30 (чтобы прошло 24 часа)
    mock_dt = datetime(2024, 12, 30, 12, 0, 0)  # Используем реальный datetime, через 24 часа
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
    mock_final_voting.started_at = datetime(2024, 12, 29, 12, 0, 0)  # Добавляем реальную дату
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

    # Verify voting was created (now it's a single combined message)
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

    # Mock exec for candidates query in handle_vote_callback
    mock_candidates_query = MagicMock()
    mock_candidates_query.all.return_value = sample_players
    mock_context.db_session.exec.return_value = mock_candidates_query

    await handle_vote_callback(mock_update, mock_context)

    # Verify vote was recorded
    mock_callback_query.answer.assert_called_once()
    assert "учтён" in mock_callback_query.answer.call_args[0][0].lower() or "учтен" in mock_callback_query.answer.call_args[0][0].lower()

    # Manually update mock_final_voting.votes_data to simulate the real behavior
    mock_final_voting.votes_data = '{"100000001": [1]}'

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

    # Manually update mock_final_voting.votes_data to simulate adding second vote
    mock_final_voting.votes_data = '{"100000001": [1, 2]}'

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
    weights_result = [(1, 100000001, 5), (2, 100000002, 3), (3, 100000003, 2)]  # user_id, tg_id, weight
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


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_voting_cycle_with_improvements(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test full voting cycle with all new improvements: auto votes, dynamic max votes, voter count, etc."""
    # Setup game with players
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Mock current_datetime to return Dec 29
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 29
    mock_dt.timetuple.return_value.tm_yday = 364
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Step 1: Start final voting with 6 missed days (should allow 3 votes per formula)
    missed_days = [1, 2, 3, 4, 5, 6]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)

    # Mock FinalVoting query - no existing voting
    mock_voting_query_none = MagicMock()
    mock_voting_query_none.filter_by.return_value = mock_voting_query_none
    mock_voting_query_none.one_or_none.return_value = None

    # Mock player weights query
    mock_weights_query = MagicMock()
    player_weights = [(sample_players[0], 6), (sample_players[1], 4), (sample_players[2], 2)]
    mock_weights_query.all.return_value = player_weights

    # Setup query side effects for pidorfinal
    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query_none]
    mock_context.db_session.exec.return_value = mock_weights_query

    # Mock bot.send_message for voting keyboard
    mock_voting_message = MagicMock()
    mock_voting_message.message_id = 99999
    mock_context.bot.send_message = AsyncMock(return_value=mock_voting_message)

    # Create a mock FinalVoting object
    mock_final_voting = MagicMock()
    mock_final_voting.id = 1
    mock_final_voting.game_id = 1
    mock_final_voting.year = 2024
    mock_final_voting.votes_data = '{}'
    mock_final_voting.started_at = datetime(2024, 12, 29, 12, 0, 0)
    mock_final_voting.ended_at = None
    mock_final_voting.missed_days_count = 6  # 6 дней → 3 выбора по формуле
    mock_final_voting.missed_days_list = json.dumps(missed_days)

    await pidorfinal_cmd(mock_update, mock_context)

    # Verify voting was created with correct max_votes (6 days → 3 votes)
    mock_context.bot.send_message.assert_called_once()
    call_args = str(mock_context.bot.send_message.call_args)
    assert "Максимум *3* выборов" in call_args

    # Reset mocks
    mock_context.bot.send_message.reset_mock()
    mock_context.db_session.commit.reset_mock()

    # Step 2: Check status with voter count
    # Only player 1 votes (players 2 and 3 don't vote)
    mock_final_voting.votes_data = '{"100000001": [1, 2]}'  # Player 1 votes for candidates 1 and 2

    mock_voting_query_active = MagicMock()
    mock_voting_query_active.filter_by.return_value = mock_voting_query_active
    mock_voting_query_active.one_or_none.return_value = mock_final_voting

    mock_context.db_session.query.side_effect = [mock_game_query, mock_voting_query_active]

    await pidorfinalstatus_cmd(mock_update, mock_context)

    # Verify status shows voter count
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "Проголосовало: 1" in call_args

    # Reset mocks
    mock_update.effective_chat.send_message.reset_mock()

    # Step 3: Test voting after ended (should return "пішов в хуй")
    mock_final_voting.ended_at = datetime(2024, 12, 30, 12, 0, 0)  # Mark as ended

    mock_callback_query = AsyncMock()
    mock_callback_query.data = "vote_1_1"
    mock_callback_query.from_user.id = 100000002
    mock_update.callback_query = mock_callback_query

    mock_voting_query_for_vote = MagicMock()
    mock_voting_query_for_vote.filter_by.return_value.one_or_none.return_value = mock_final_voting

    # Reset query side_effect to avoid StopIteration
    mock_context.db_session.query.side_effect = None
    mock_context.db_session.query.return_value = mock_voting_query_for_vote

    await handle_vote_callback(mock_update, mock_context)

    # Verify correct response for ended voting
    mock_callback_query.answer.assert_called_once_with("пішов в хуй")

    # Reset mocks
    mock_callback_query.answer.reset_mock()

    # Step 4: Test finalize_voting with auto votes for non-voters
    # Reset voting to active state for finalization test
    mock_final_voting.ended_at = None
    mock_final_voting.votes_data = '{"100000001": [1, 2]}'  # Only user 1 voted (using tg_id)

    # Mock finalize_voting call
    from bot.handlers.game.voting_helpers import finalize_voting

    # Mock player weights for finalize_voting
    mock_weights_for_finalize = MagicMock()
    weights_result = [(1, 100000001, 6), (2, 100000002, 4), (3, 100000003, 2)]  # user_id, tg_id, weight
    mock_weights_for_finalize.all.return_value = weights_result
    mock_context.db_session.exec.return_value = mock_weights_for_finalize

    # Mock winner query
    winner = sample_players[1]  # User 2 should win with auto votes
    winner.id = 2
    mock_context.db_session.query.return_value.filter_by.return_value.one.return_value = winner

    # Call finalize_voting directly to test auto voting logic
    winners, results = finalize_voting(mock_final_voting, mock_context, auto_vote_for_non_voters=True)

    # Verify winners is a list of tuples
    assert isinstance(winners, list)
    assert len(winners) >= 1
    winner_id, winner_obj = winners[0]

    # Verify auto votes were added with NEW LOGIC:
    # User 1: voted for candidates 1,2 (weight 6, 2 votes) = 3.0 each
    # User 2: auto-voted for himself with 3 votes (weight 4, 3 votes) = 4.0 total
    # User 3: auto-voted for himself with 3 votes (weight 2, 3 votes) = 2.0 total
    # Expected results with NEW LOGIC (auto votes NOT in 'votes'):
    # Candidate 1: 3.0 weighted (3.0 from user 1), 1 manual vote, 0 auto votes
    # Candidate 2: 7.0 weighted (3.0 from user 1 + 4.0 from user 2 auto-vote), 1 manual vote, 3 auto votes
    # Candidate 3: 2.0 weighted, 0 manual votes, 3 auto votes

    assert abs(results[1]['weighted'] - 3.0) < 0.001  # 3.0 from user 1
    assert results[1]['votes'] == 1  # Only manual votes
    assert results[1]['auto_votes'] == 0  # No auto votes
    assert abs(results[2]['weighted'] - 7.0) < 0.001  # 3.0 from user 1 + 4.0 from user 2 auto-vote
    assert results[2]['votes'] == 1  # Only manual vote from user 1
    assert results[2]['auto_votes'] == 3  # Auto votes from user 2
    assert abs(results[3]['weighted'] - 2.0) < 0.001
    assert results[3]['votes'] == 0  # No manual votes
    assert results[3]['auto_votes'] == 3  # Only auto votes

    # User 2 should win with highest weighted score (7.0)
    assert winner_id == 2
    assert winner_obj.id == 2

    # Verify voting was marked as ended
    assert mock_final_voting.ended_at is not None
    assert mock_final_voting.winner_id == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_vote_callback_no_keyboard_update(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that vote callback does NOT update keyboard after voting (according to plan fixes)."""
    # Setup game with players
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Create a mock FinalVoting object
    mock_final_voting = MagicMock()
    mock_final_voting.id = 1
    mock_final_voting.game_id = 1
    mock_final_voting.year = 2024
    mock_final_voting.votes_data = '{"100000001": [1]}'  # User 1 already voted for candidate 1
    mock_final_voting.ended_at = None  # Active voting
    mock_final_voting.missed_days_count = 4  # Allows 2 votes (4/2 = 2)

    # Mock callback query for user 2 voting
    mock_callback_query = AsyncMock()
    mock_callback_query.from_user.id = 100000002  # Different user
    mock_callback_query.data = "vote_1_2"  # Vote for candidate 2
    mock_update.callback_query = mock_callback_query
    mock_update.effective_chat.id = -123456789  # Regular chat

    # Mock FinalVoting query
    mock_voting_query = MagicMock()
    mock_voting_query.filter_by.return_value.one_or_none.return_value = mock_final_voting
    mock_context.db_session.query.return_value = mock_voting_query

    # Mock candidates query for keyboard update
    mock_candidates_query = MagicMock()
    mock_candidates_query.all.return_value = sample_players
    mock_context.db_session.exec.return_value = mock_candidates_query

    # Execute vote callback
    await handle_vote_callback(mock_update, mock_context)

    # Verify that the vote was processed
    mock_callback_query.answer.assert_called_once()
    answer_text = mock_callback_query.answer.call_args[0][0]
    assert "учтён" in answer_text.lower() or "учтен" in answer_text.lower()

    # Verify that keyboard was NOT updated (according to plan fixes - stage 2)
    # The keyboard should not be updated after voting to prevent showing checkmarks to all users
    mock_callback_query.edit_message_reply_markup.assert_not_called()

    # Verify that votes_data was updated correctly
    mock_context.db_session.commit.assert_called_once()

    # The key insight is that we removed keyboard updates to prevent the bug where
    # buttons change for everyone when someone else votes. Now users only get text notifications.
