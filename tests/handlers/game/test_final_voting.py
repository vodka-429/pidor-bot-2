"""Tests for final voting functionality."""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from bot.handlers.game.commands import (
    pidorfinal_cmd,
    handle_poll_answer,
    pidorfinalstatus_cmd
)
from bot.app.models import FinalVoting, GameResult, TGUser


@pytest.mark.unit
def test_pidorfinal_cmd_wrong_date(mock_update, mock_context, mock_game, mocker):
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
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "29 или 30 декабря" in call_args or "wrong date" in call_args.lower()


@pytest.mark.unit
def test_pidorfinal_cmd_too_many_missed_days(mock_update, mock_context, mock_game, mocker):
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
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "Слишком много" in call_args or "too many" in call_args.lower()


@pytest.mark.unit
def test_pidorfinal_cmd_already_exists(mock_update, mock_context, mock_game, mocker):
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
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify error message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "уже запущено" in call_args or "already exists" in call_args.lower()


@pytest.mark.unit
def test_pidorfinal_cmd_success(mock_update, mock_context, mock_game, sample_players, mocker):
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
    
    # Mock bot.send_poll
    mock_poll = MagicMock()
    mock_poll.poll.id = "test_poll_id"
    mock_poll.message_id = 12345
    mock_context.bot.send_poll = MagicMock(return_value=mock_poll)
    
    # Execute
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify info message was sent
    assert mock_update.effective_chat.send_message.call_count == 1
    
    # Verify poll was created
    mock_context.bot.send_poll.assert_called_once()
    
    # Verify FinalVoting was added to session
    mock_context.db_session.add.assert_called_once()
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.unit
def test_pidorfinal_cmd_test_chat_bypass_date_check(mock_update, mock_context, mock_game, sample_players, mocker):
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
    
    # Mock bot.send_poll
    mock_poll = MagicMock()
    mock_poll.poll.id = "test_poll_id"
    mock_poll.message_id = 12345
    mock_context.bot.send_poll = MagicMock(return_value=mock_poll)
    
    # Execute
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify info message was sent (not error about wrong date)
    assert mock_update.effective_chat.send_message.call_count == 1
    call_args = str(mock_update.effective_chat.send_message.call_args)
    # Should NOT contain date error
    assert "29 или 30 декабря" not in call_args
    
    # Verify poll was created
    mock_context.bot.send_poll.assert_called_once()
    
    # Verify FinalVoting was added to session
    mock_context.db_session.add.assert_called_once()
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.unit
def test_pidorfinal_cmd_test_chat_bypass_missed_days_check(mock_update, mock_context, mock_game, sample_players, mocker):
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
    
    # Mock bot.send_poll
    mock_poll = MagicMock()
    mock_poll.poll.id = "test_poll_id"
    mock_poll.message_id = 12345
    mock_context.bot.send_poll = MagicMock(return_value=mock_poll)
    
    # Execute
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify info message was sent (not error about too many days)
    assert mock_update.effective_chat.send_message.call_count == 1
    call_args = str(mock_update.effective_chat.send_message.call_args)
    # Should NOT contain "too many" error
    assert "Слишком много" not in call_args
    
    # Verify poll was created
    mock_context.bot.send_poll.assert_called_once()
    
    # Verify FinalVoting was added to session
    mock_context.db_session.add.assert_called_once()
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.unit
def test_pidorfinal_cmd_regular_chat_date_check_enforced(mock_update, mock_context, mock_game, mocker):
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
    pidorfinal_cmd(mock_update, mock_context)
    
    # Verify error message about wrong date was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "29 или 30 декабря" in call_args or "wrong date" in call_args.lower()


@pytest.mark.unit
def test_handle_poll_answer_not_closed(mock_update, mock_context, mocker):
    """Test handle_poll_answer does nothing when poll is not closed."""
    # Setup
    mock_update.poll.id = "test_poll_id"
    mock_update.poll.is_closed = False
    
    # Mock FinalVoting query
    mock_voting = MagicMock()
    mock_voting.ended_at = None
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_voting
    
    # Execute
    handle_poll_answer(mock_update, mock_context)
    
    # Verify no message was sent (poll not closed yet)
    mock_context.bot.send_message.assert_not_called()


@pytest.mark.unit
def test_handle_poll_answer_closed(mock_update, mock_context, sample_players, mocker):
    """Test handle_poll_answer processes closed poll correctly."""
    # Setup
    mock_update.poll.id = "test_poll_id"
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
    
    # Mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.ended_at = None
    mock_voting.missed_days_count = 5
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4, 5])
    
    # Mock Game query
    mock_game = MagicMock()
    mock_game.chat_id = 987654321
    
    # Mock player weights
    mock_weights_query = MagicMock()
    player_weights = [(sample_players[0], 5), (sample_players[1], 3), (sample_players[2], 2)]
    mock_weights_query.all.return_value = player_weights
    
    # Mock final stats query
    mock_stats_query = MagicMock()
    final_stats = [(sample_players[0], 10), (sample_players[1], 8), (sample_players[2], 7)]
    mock_stats_query.all.return_value = final_stats
    
    # Setup query side effects
    def query_side_effect(model):
        if model == FinalVoting:
            mock_q = MagicMock()
            mock_q.filter_by.return_value.one_or_none.return_value = mock_voting
            return mock_q
        elif model == mock_game.__class__:
            mock_q = MagicMock()
            mock_q.filter_by.return_value.one.return_value = mock_game
            return mock_q
        return MagicMock()
    
    mock_context.db_session.query.side_effect = query_side_effect
    mock_context.db_session.exec.side_effect = [mock_weights_query, mock_stats_query]
    
    # Mock current_datetime
    mock_dt = datetime(2024, 12, 30, 12, 0, 0)
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    handle_poll_answer(mock_update, mock_context)
    
    # Verify FinalVoting was updated
    assert mock_voting.ended_at is not None
    assert mock_voting.winner_id is not None
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called()
    
    # Verify results message was sent
    mock_context.bot.send_message.assert_called_once()


@pytest.mark.unit
def test_weighted_votes_calculation(sample_players):
    """Test weighted votes calculation logic."""
    # Setup voting results
    votes = {
        "@player1": 2,  # 2 votes
        "@player2": 1,  # 1 vote
        "@player3": 1,  # 1 vote
    }
    
    # Setup weights (wins in the year)
    weights = {
        "@player1": 5,
        "@player2": 3,
        "@player3": 2,
    }
    
    # Calculate weighted votes
    weighted_votes = {}
    for player, vote_count in votes.items():
        weight = weights.get(player, 1)
        weighted_votes[player] = vote_count * weight
    
    # Verify calculations
    assert weighted_votes["@player1"] == 10  # 2 * 5
    assert weighted_votes["@player2"] == 3   # 1 * 3
    assert weighted_votes["@player3"] == 2   # 1 * 2
    
    # Verify winner
    winner = max(weighted_votes, key=weighted_votes.get)
    assert winner == "@player1"


@pytest.mark.unit
def test_pidorfinalstatus_cmd_not_started(mock_update, mock_context, mock_game, mocker):
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
    pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "not started" message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "не запущено" in call_args or "not started" in call_args.lower()


@pytest.mark.unit
def test_pidorfinalstatus_cmd_active(mock_update, mock_context, mock_game, mocker):
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
    pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "active" message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "активно" in call_args or "active" in call_args.lower()


@pytest.mark.unit
def test_pidorfinalstatus_cmd_completed(mock_update, mock_context, mock_game, mock_tg_user, mocker):
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
    pidorfinalstatus_cmd(mock_update, mock_context)
    
    # Verify "completed" message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "завершено" in call_args or "completed" in call_args.lower()
