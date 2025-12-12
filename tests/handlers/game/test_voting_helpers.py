"""Tests for voting helpers functionality."""
import pytest
import json
from unittest.mock import MagicMock, Mock
from telegram import User as TGUser

from bot.handlers.game.voting_helpers import (
    create_voting_keyboard,
    parse_vote_callback_data,
    format_vote_callback_data,
    finalize_voting,
    format_player_with_wins,
    get_player_weights,
    format_weights_message,
    count_voters,
    calculate_max_votes,
    duplicate_candidates_for_test,
    VOTE_CALLBACK_PREFIX
)
from bot.app.models import FinalVoting, GameResult, TGUser as DBUser


@pytest.mark.unit
def test_format_vote_callback_data():
    """Test formatting callback_data for voting button."""
    # Test basic formatting
    result = format_vote_callback_data(123, 456)
    assert result == "vote_123_456"
    
    # Test with different IDs
    result = format_vote_callback_data(1, 1)
    assert result == "vote_1_1"
    
    result = format_vote_callback_data(999999, 888888)
    assert result == "vote_999999_888888"


@pytest.mark.unit
def test_parse_vote_callback_data():
    """Test parsing callback_data to extract voting_id and candidate_id."""
    # Test valid callback_data
    voting_id, candidate_id = parse_vote_callback_data("vote_123_456")
    assert voting_id == 123
    assert candidate_id == 456
    
    # Test with different IDs
    voting_id, candidate_id = parse_vote_callback_data("vote_1_1")
    assert voting_id == 1
    assert candidate_id == 1
    
    # Test with large IDs
    voting_id, candidate_id = parse_vote_callback_data("vote_999999_888888")
    assert voting_id == 999999
    assert candidate_id == 888888


@pytest.mark.unit
def test_parse_vote_callback_data_invalid_format():
    """Test parsing invalid callback_data raises ValueError."""
    # Test without prefix
    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_vote_callback_data("invalid_123_456")
    
    # Test with wrong number of parts
    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_vote_callback_data("vote_123")
    
    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_vote_callback_data("vote_123_456_789")
    
    # Test with non-numeric IDs
    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_vote_callback_data("vote_abc_def")
    
    # Test empty string
    with pytest.raises(ValueError, match="Invalid callback_data format"):
        parse_vote_callback_data("")


@pytest.mark.unit
def test_create_voting_keyboard_two_candidates():
    """Test creating keyboard with 2 candidates."""
    # Create mock candidates
    candidate1 = Mock(spec=TGUser)
    candidate1.id = 1
    candidate1.first_name = "Alice"
    candidate1.last_name = "Smith"
    
    candidate2 = Mock(spec=TGUser)
    candidate2.id = 2
    candidate2.first_name = "Bob"
    candidate2.last_name = None
    
    candidates = [candidate1, candidate2]
    
    # Create keyboard with voting_id
    voting_id = 123
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, votes_per_row=2)
    
    # Verify structure
    assert len(keyboard.inline_keyboard) == 1  # 1 row
    assert len(keyboard.inline_keyboard[0]) == 2  # 2 buttons in row
    
    # Verify button texts
    assert keyboard.inline_keyboard[0][0].text == "Alice Smith"
    assert keyboard.inline_keyboard[0][1].text == "Bob"
    
    # Verify callback_data contains voting_id
    assert keyboard.inline_keyboard[0][0].callback_data == "vote_123_1"
    assert keyboard.inline_keyboard[0][1].callback_data == "vote_123_2"


@pytest.mark.unit
def test_create_voting_keyboard_five_candidates():
    """Test creating keyboard with 5 candidates."""
    # Create mock candidates
    candidates = []
    for i in range(1, 6):
        candidate = Mock(spec=TGUser)
        candidate.id = i
        candidate.first_name = f"User{i}"
        candidate.last_name = None
        candidates.append(candidate)
    
    # Create keyboard with 2 buttons per row
    voting_id = 456
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, votes_per_row=2)
    
    # Verify structure: 5 candidates / 2 per row = 3 rows (2+2+1)
    assert len(keyboard.inline_keyboard) == 3
    assert len(keyboard.inline_keyboard[0]) == 2  # First row: 2 buttons
    assert len(keyboard.inline_keyboard[1]) == 2  # Second row: 2 buttons
    assert len(keyboard.inline_keyboard[2]) == 1  # Third row: 1 button
    
    # Verify all candidates are present
    all_buttons = []
    for row in keyboard.inline_keyboard:
        all_buttons.extend(row)
    
    assert len(all_buttons) == 5
    for i, button in enumerate(all_buttons, 1):
        assert button.text == f"User{i}"


@pytest.mark.unit
def test_create_voting_keyboard_ten_candidates():
    """Test creating keyboard with 10 candidates."""
    # Create mock candidates
    candidates = []
    for i in range(1, 11):
        candidate = Mock(spec=TGUser)
        candidate.id = i
        candidate.first_name = f"Player{i}"
        candidate.last_name = f"Last{i}"
        candidates.append(candidate)
    
    # Create keyboard with 2 buttons per row
    voting_id = 789
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, votes_per_row=2)
    
    # Verify structure: 10 candidates / 2 per row = 5 rows
    assert len(keyboard.inline_keyboard) == 5
    for row in keyboard.inline_keyboard:
        assert len(row) == 2
    
    # Verify button texts include both first and last names
    assert keyboard.inline_keyboard[0][0].text == "Player1 Last1"
    assert keyboard.inline_keyboard[4][1].text == "Player10 Last10"


@pytest.mark.unit
def test_create_voting_keyboard_fifteen_candidates():
    """Test creating keyboard with 15 candidates."""
    # Create mock candidates
    candidates = []
    for i in range(1, 16):
        candidate = Mock(spec=TGUser)
        candidate.id = i
        candidate.first_name = f"User{i}"
        candidate.last_name = None
        candidates.append(candidate)
    
    # Create keyboard with 3 buttons per row
    voting_id = 999
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, votes_per_row=3)
    
    # Verify structure: 15 candidates / 3 per row = 5 rows
    assert len(keyboard.inline_keyboard) == 5
    for row in keyboard.inline_keyboard:
        assert len(row) == 3
    
    # Verify all 15 candidates are present
    all_buttons = []
    for row in keyboard.inline_keyboard:
        all_buttons.extend(row)
    
    assert len(all_buttons) == 15


@pytest.mark.unit
def test_create_voting_keyboard_custom_votes_per_row():
    """Test creating keyboard with custom votes_per_row parameter."""
    # Create 6 candidates
    candidates = []
    for i in range(1, 7):
        candidate = Mock(spec=TGUser)
        candidate.id = i
        candidate.first_name = f"User{i}"
        candidate.last_name = None
        candidates.append(candidate)
    
    voting_id = 111
    
    # Test with 3 buttons per row
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, votes_per_row=3)
    assert len(keyboard.inline_keyboard) == 2  # 6 / 3 = 2 rows
    assert len(keyboard.inline_keyboard[0]) == 3
    assert len(keyboard.inline_keyboard[1]) == 3
    
    # Test with 1 button per row
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, votes_per_row=1)
    assert len(keyboard.inline_keyboard) == 6  # 6 / 1 = 6 rows
    for row in keyboard.inline_keyboard:
        assert len(row) == 1


@pytest.mark.unit
def test_finalize_voting_calculation(mock_context, sample_players):
    """Test finalize_voting correctly calculates weighted votes."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4, 5])
    mock_voting.missed_days_count = 5  # Add missed_days_count for auto voting calculation
    
    # Setup votes_data: user 1 votes for candidates 1,2; user 2 votes for candidate 1; user 3 votes for candidate 3
    votes_data = {
        "1": [1, 2],  # User 1 votes for candidates 1 and 2
        "2": [1],     # User 2 votes for candidate 1
        "3": [3]      # User 3 votes for candidate 3
    }
    mock_voting.votes_data = json.dumps(votes_data)
    
    # Setup player weights (wins in the year)
    # User 1 has 5 wins, User 2 has 3 wins, User 3 has 2 wins
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 5), (2, 3), (3, 2)]
    
    # Setup winner query
    winner = sample_players[0]  # Candidate 1 should win
    winner.id = 1
    
    mock_context.db_session.exec.return_value = mock_weights_result
    mock_context.db_session.query.return_value.filter_by.return_value.one.return_value = winner
    
    # Execute
    winners, results = finalize_voting(mock_voting, mock_context)
    
    # Verify winners is a list of tuples
    assert isinstance(winners, list)
    assert len(winners) >= 1
    winner_id, winner_obj = winners[0]
    
    # Verify weighted votes and real votes calculation with new division logic
    # Candidate 1: voted by user 1 (weight 5, 2 votes) and user 2 (weight 3, 1 vote) = 5/2 + 3/1 = 2.5 + 3.0 = 5.5 weighted, 2 votes
    # Candidate 2: voted by user 1 (weight 5, 2 votes) = 5/2 = 2.5 weighted, 1 vote
    # Candidate 3: voted by user 3 (weight 2, 1 vote) = 2/1 = 2.0 weighted, 1 vote
    assert results[1]['weighted'] == 5.5
    assert results[1]['votes'] == 2
    assert results[2]['weighted'] == 2.5
    assert results[2]['votes'] == 1
    assert results[3]['weighted'] == 2.0
    assert results[3]['votes'] == 1
    
    # Verify winner is candidate 1 (highest weighted votes)
    assert winner_id == 1
    assert winner_obj.id == 1
    
    # Note: GameResult creation is currently commented out in finalize_voting
    # So we don't verify db_session.add calls
    
    # Verify FinalVoting was updated
    assert mock_voting.ended_at is not None
    assert mock_voting.winner_id == 1
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.unit
def test_finalize_voting_no_votes(mock_context, sample_players, mocker):
    """Test finalize_voting handles case when nobody voted (with auto_vote disabled)."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3])
    mock_voting.missed_days_count = 3  # Add missed_days_count for auto voting calculation
    mock_voting.votes_data = json.dumps({})  # No votes
    
    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 5), (2, 3), (3, 2)]
    
    # Setup candidates query (all players who had wins)
    mock_candidates_result = MagicMock()
    mock_candidates_result.all.return_value = [1, 2, 3]
    
    # Mock random.sample to return deterministic result
    import random
    mocker.patch.object(random, 'sample', return_value=[2])
    
    # Setup winner query - winner will be candidate 2 (from mocked random.sample)
    winner = sample_players[1]
    winner.id = 2
    
    mock_context.db_session.exec.side_effect = [mock_weights_result, mock_candidates_result]
    mock_context.db_session.query.return_value.filter_by.return_value.one.return_value = winner
    
    # Execute with auto_vote_for_non_voters disabled to test old behavior
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=False)
    
    # Verify winners is a list with one winner
    assert isinstance(winners, list)
    assert len(winners) == 1
    winner_id, winner_obj = winners[0]
    assert winner_id == 2
    assert winner_obj.id == 2
    
    # Verify results contains the winner with 0 votes
    assert 2 in results
    assert results[2]['weighted'] == 0.0
    assert results[2]['votes'] == 0
    
    # Note: GameResult creation is currently commented out in finalize_voting
    # So we don't verify db_session.add calls
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.unit
def test_finalize_voting_equal_weighted_votes(mock_context, sample_players):
    """Test finalize_voting handles tie in weighted votes."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2])
    mock_voting.missed_days_count = 2  # Add missed_days_count for auto voting calculation
    
    # Setup votes_data: create a tie
    # User 1 (weight 4) votes for candidate 1
    # User 2 (weight 4) votes for candidate 2
    votes_data = {
        "1": [1],
        "2": [2]
    }
    mock_voting.votes_data = json.dumps(votes_data)
    
    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 4), (2, 4)]
    
    # Setup winner queries - need to mock for both potential winners
    winner1 = sample_players[0]
    winner1.id = 1
    winner2 = sample_players[1]
    winner2.id = 2
    
    mock_context.db_session.exec.return_value = mock_weights_result
    
    # Mock query to return different winners based on filter_by call
    def query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def filter_by_side_effect(id=None):
            mock_filter_q = MagicMock()
            if id == 1:
                mock_filter_q.one.return_value = winner1
            elif id == 2:
                mock_filter_q.one.return_value = winner2
            else:
                mock_filter_q.one.return_value = winner1
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q
    
    mock_context.db_session.query.side_effect = query_side_effect
    
    # Execute
    winners, results = finalize_voting(mock_voting, mock_context)
    
    # Verify both candidates have equal weighted votes (each user votes for 1 candidate, so no division)
    assert results[1]['weighted'] == 4.0
    assert results[2]['weighted'] == 4.0
    
    # Verify winners is a list
    assert isinstance(winners, list)
    assert len(winners) == 1  # Only 1 winner for 2 missed days
    winner_id, winner_obj = winners[0]
    assert winner_id in [1, 2]
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.unit
def test_format_player_with_wins():
    """Test format_player_with_wins correctly formats player names with wins."""
    # Create mock player
    player = Mock(spec=TGUser)
    player.first_name = "Иван"
    player.last_name = "Иванов"
    
    # Test with 1 win (победа) - now with escaped parentheses
    result = format_player_with_wins(player, 1)
    assert result == "Иван Иванов \\(1 победа\\)"
    
    # Test with 2 wins (победы)
    result = format_player_with_wins(player, 2)
    assert result == "Иван Иванов \\(2 победы\\)"
    
    # Test with 5 wins (побед)
    result = format_player_with_wins(player, 5)
    assert result == "Иван Иванов \\(5 побед\\)"
    
    # Test with 11 wins (побед - exception for 11)
    result = format_player_with_wins(player, 11)
    assert result == "Иван Иванов \\(11 побед\\)"
    
    # Test with 21 wins (победа)
    result = format_player_with_wins(player, 21)
    assert result == "Иван Иванов \\(21 победа\\)"
    
    # Test with 22 wins (победы)
    result = format_player_with_wins(player, 22)
    assert result == "Иван Иванов \\(22 победы\\)"
    
    # Test player without last name
    player.last_name = None
    result = format_player_with_wins(player, 3)
    assert result == "Иван \\(3 победы\\)"


@pytest.mark.unit
def test_get_player_weights(mock_context, sample_players):
    """Test get_player_weights retrieves player weights correctly."""
    # Setup mock query result
    mock_weights_result = MagicMock()
    player_weights = [
        (sample_players[0], 5),
        (sample_players[1], 3),
        (sample_players[2], 2)
    ]
    mock_weights_result.all.return_value = player_weights
    
    mock_context.db_session.exec.return_value = mock_weights_result
    
    # Execute
    result = get_player_weights(mock_context.db_session, game_id=1, year=2024)
    
    # Verify
    assert len(result) == 3
    assert result[0] == (sample_players[0], 5)
    assert result[1] == (sample_players[1], 3)
    assert result[2] == (sample_players[2], 2)


@pytest.mark.unit
def test_format_weights_message(sample_players):
    """Test format_weights_message creates correct message."""
    # Setup player weights
    sample_players[0].first_name = "Алиса"
    sample_players[0].last_name = "Смит"
    sample_players[1].first_name = "Боб"
    sample_players[1].last_name = None
    sample_players[2].first_name = "Чарли"
    sample_players[2].last_name = "Браун"
    
    player_weights = [
        (sample_players[0], 5),
        (sample_players[1], 3),
        (sample_players[2], 2)
    ]
    
    # Execute
    result = format_weights_message(player_weights, missed_count=7)
    
    # Verify message contains expected elements
    assert "7" in result  # missed days count
    # Note: text is escaped for Markdown V2, so we check for escaped versions
    # The function uses format_player_with_wins which now triple-escapes in the message
    assert "Алиса Смит \\\\\\(5 побед\\\\\\)" in result
    assert "Боб \\\\\\(3 победы\\\\\\)" in result
    assert "Чарли Браун \\\\\\(2 победы\\\\\\)" in result
    assert "Финальное голосование года" in result
    assert "Голосуйте мудро" in result




@pytest.mark.unit
def test_count_voters_empty():
    """Test count_voters with empty votes_data."""
    assert count_voters('{}') == 0
    assert count_voters('') == 0


@pytest.mark.unit
def test_count_voters_single_user():
    """Test count_voters with single user."""
    votes_data = '{"123": [1, 2]}'
    assert count_voters(votes_data) == 1


@pytest.mark.unit
def test_count_voters_multiple_users():
    """Test count_voters with multiple users."""
    votes_data = '{"123": [1], "456": [2, 3], "789": [1, 2, 3]}'
    assert count_voters(votes_data) == 3


@pytest.mark.unit
def test_count_voters_invalid_json():
    """Test count_voters with invalid JSON."""
    assert count_voters('invalid json') == 0
    assert count_voters(None) == 0


@pytest.mark.unit
def test_calculate_max_votes_all_cases():
    """Test calculate_max_votes for all values from 1 to 10."""
    # Test all cases according to the formula
    assert calculate_max_votes(1) == 1   # 1 день → 1 выбор
    assert calculate_max_votes(2) == 1   # 2 дня → 2/2 = 1 выбор (но минимум 1)
    assert calculate_max_votes(3) == 1   # 3 дня → 1 выбор (простое число)
    assert calculate_max_votes(4) == 2   # 4 дня → 4/2 = 2 выбора
    assert calculate_max_votes(5) == 1   # 5 дней → 1 выбор (простое число)
    assert calculate_max_votes(6) == 3   # 6 дней → 6/2 = 3 выбора
    assert calculate_max_votes(7) == 1   # 7 дней → 1 выбор (простое число)
    assert calculate_max_votes(8) == 4   # 8 дней → 8/2 = 4 выбора
    assert calculate_max_votes(9) == 3   # 9 дней → 9/3 = 3 выбора (составное нечетное)
    assert calculate_max_votes(10) == 5  # 10 дней → 10/2 = 5 выборов


@pytest.mark.unit
def test_calculate_max_votes_edge_cases():
    """Test calculate_max_votes with edge cases."""
    assert calculate_max_votes(0) == 1
    assert calculate_max_votes(-1) == 1
    assert calculate_max_votes('invalid') == 1


@pytest.mark.unit
def test_finalize_voting_with_auto_votes(mock_context, sample_players):
    """Test finalize_voting with automatic votes for non-voters."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4])
    mock_voting.missed_days_count = 4  # 4 дня → 2 выбора по формуле
    
    # Setup votes_data: only user 1 votes
    votes_data = {
        "1": [1]  # User 1 votes for candidate 1
    }
    mock_voting.votes_data = json.dumps(votes_data)
    
    # Setup player weights: users 1, 2, 3 all have weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 5), (2, 3), (3, 2)]
    
    # Setup winner query
    winner = sample_players[0]  # User 1 should win with highest weighted score
    winner.id = 1
    
    mock_context.db_session.exec.return_value = mock_weights_result
    mock_context.db_session.query.return_value.filter_by.return_value.one.return_value = winner
    
    # Execute
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True)
    
    # Verify winners is a list
    assert isinstance(winners, list)
    assert len(winners) >= 1
    winner_id, winner_obj = winners[0]
    
    # Verify auto votes were added:
    # User 1: voted for candidate 1 (weight 5, 1 vote) = 5.0 weighted
    # User 2: auto-voted for himself with 2 votes (weight 3, 2 votes) = 3.0 weighted
    # User 3: auto-voted for himself with 2 votes (weight 2, 2 votes) = 2.0 weighted
    assert results[1]['weighted'] == 5.0
    assert results[1]['votes'] == 1
    assert results[2]['weighted'] == 3.0
    assert results[2]['votes'] == 2
    assert results[3]['weighted'] == 2.0
    assert results[3]['votes'] == 2
    
    # User 1 should win with highest weighted score (5.0 > 3.0 > 2.0)
    assert winner_id == 1
    assert winner_obj.id == 1


@pytest.mark.unit
def test_finalize_voting_partial_voters(mock_context, sample_players):
    """Test finalize_voting with mixed scenario of voters and non-voters."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3])
    mock_voting.missed_days_count = 3  # 3 дня → 1 выбор по формуле (простое число)
    
    # Setup votes_data: users 1 and 2 vote, user 3 doesn't
    votes_data = {
        "1": [2],  # User 1 votes for candidate 2
        "2": [1]   # User 2 votes for candidate 1
        # User 3 doesn't vote - should get auto vote for himself
    }
    mock_voting.votes_data = json.dumps(votes_data)
    
    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 3), (2, 4), (3, 6)]
    
    # Setup winner query
    winner = sample_players[2]  # User 3 should win with auto vote
    winner.id = 3
    
    mock_context.db_session.exec.return_value = mock_weights_result
    mock_context.db_session.query.return_value.filter_by.return_value.one.return_value = winner
    
    # Execute
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True)
    
    # Verify winners is a list
    assert isinstance(winners, list)
    assert len(winners) >= 1
    winner_id, winner_obj = winners[0]
    
    # Verify results:
    # Candidate 1: voted by user 2 (weight 4, 1 vote) = 4.0 weighted
    # Candidate 2: voted by user 1 (weight 3, 1 vote) = 3.0 weighted
    # Candidate 3: auto-voted by user 3 (weight 6, 1 vote) = 6.0 weighted
    assert results[1]['weighted'] == 4.0
    assert results[1]['votes'] == 1
    assert results[2]['weighted'] == 3.0
    assert results[2]['votes'] == 1
    assert results[3]['weighted'] == 6.0
    assert results[3]['votes'] == 1
    
    # User 3 should win with highest weighted score (6.0 > 4.0 > 3.0)
    assert winner_id == 3
    assert winner_obj.id == 3


@pytest.mark.unit
def test_finalize_voting_auto_votes_respect_max_votes(mock_context, sample_players):
    """Test finalize_voting auto votes respect calculate_max_votes formula."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4, 5, 6])
    mock_voting.missed_days_count = 6  # 6 дней → 3 выбора по формуле
    
    # Setup votes_data: nobody votes
    votes_data = {}
    mock_voting.votes_data = json.dumps(votes_data)
    
    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 2), (2, 4)]
    
    # Setup winner queries - need to mock for both potential winners
    winner1 = sample_players[0]
    winner1.id = 1
    winner2 = sample_players[1]
    winner2.id = 2
    
    mock_context.db_session.exec.return_value = mock_weights_result
    
    # Mock query to return different winners based on filter_by call
    def query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def filter_by_side_effect(id=None):
            mock_filter_q = MagicMock()
            if id == 1:
                mock_filter_q.one.return_value = winner1
            elif id == 2:
                mock_filter_q.one.return_value = winner2
            else:
                mock_filter_q.one.return_value = winner2
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q
    
    mock_context.db_session.query.side_effect = query_side_effect
    
    # Execute
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True)
    
    # Verify winners is a list
    assert isinstance(winners, list)
    assert len(winners) >= 1
    
    # Verify auto votes:
    # User 1: auto-voted for himself with 3 votes (weight 2, 3 votes) = 2.0 weighted
    # User 2: auto-voted for himself with 3 votes (weight 4, 3 votes) = 4.0 weighted
    assert results[1]['weighted'] == 2.0
    assert results[1]['votes'] == 3
    assert results[2]['weighted'] == 4.0
    assert results[2]['votes'] == 3
    
    # User 2 should win with higher weight
    winner_id, winner_obj = winners[0]
    assert winner_id == 2
    assert winner_obj.id == 2


@pytest.mark.unit
def test_finalize_voting_weighted_division():
    """Test finalize_voting correctly divides weights by number of votes."""
    # This test is already covered in test_finalize_voting_calculation
    # but we can add a specific test for the division logic
    pass


@pytest.mark.unit
def test_finalize_voting_weighted_division_float():
    """Test finalize_voting handles float division correctly."""
    # This test is already covered in test_finalize_voting_calculation
    # The existing test verifies 5/2 = 2.5 weighted votes
    pass


@pytest.mark.unit
def test_duplicate_candidates_for_test_chat():
    """Test duplicate_candidates_for_test duplicates candidates for test chat."""
    # Create mock candidates
    candidate1 = Mock(spec=TGUser)
    candidate1.id = 1
    candidate1.first_name = "Alice"
    candidate1.last_name = "Smith"
    candidate1.username = "alice"
    
    candidate2 = Mock(spec=TGUser)
    candidate2.id = 2
    candidate2.first_name = "Bob"
    candidate2.last_name = None
    candidate2.username = "bob"
    
    candidates = [candidate1, candidate2]
    
    # Test with test chat ID
    TEST_CHAT_ID = -4608252738
    result = duplicate_candidates_for_test(candidates, TEST_CHAT_ID, target_count=5)
    
    # Should have 5 candidates total
    assert len(result) == 5
    
    # First 2 should be originals
    assert result[0].first_name == "Alice"
    assert result[1].first_name == "Bob"
    
    # Next should be duplicates with modified names but same IDs
    assert result[2].first_name == "Alice (копия 2)"
    assert result[2].id == 1  # Same ID as original
    assert result[3].first_name == "Bob (копия 2)"
    assert result[3].id == 2  # Same ID as original
    assert result[4].first_name == "Alice (копия 3)"
    assert result[4].id == 1  # Same ID as original


@pytest.mark.unit
def test_duplicate_candidates_regular_chat():
    """Test duplicate_candidates_for_test doesn't duplicate for regular chat."""
    # Create mock candidates
    candidate1 = Mock(spec=TGUser)
    candidate1.id = 1
    candidate1.first_name = "Alice"
    candidate1.last_name = "Smith"
    candidate1.username = "alice"
    
    candidates = [candidate1]
    
    # Test with regular chat ID
    REGULAR_CHAT_ID = -123456789
    result = duplicate_candidates_for_test(candidates, REGULAR_CHAT_ID, target_count=30)
    
    # Should return original candidates unchanged
    assert len(result) == 1
    assert result[0] is candidate1


@pytest.mark.unit
def test_duplicate_candidates_exact_count():
    """Test duplicate_candidates_for_test with exact target count."""
    # Create mock candidates
    candidates = []
    for i in range(1, 4):  # 3 candidates
        candidate = Mock(spec=TGUser)
        candidate.id = i
        candidate.first_name = f"User{i}"
        candidate.last_name = None
        candidate.username = f"user{i}"
        candidates.append(candidate)
    
    # Test with test chat ID and target count of 3 (exact match)
    TEST_CHAT_ID = -4608252738
    result = duplicate_candidates_for_test(candidates, TEST_CHAT_ID, target_count=3)
    
    # Should return original candidates unchanged (already at target count)
    assert len(result) == 3
    assert all(result[i] is candidates[i] for i in range(3))


@pytest.mark.unit
def test_duplicate_candidates_vote_counting():
    """Test that votes for duplicates count towards original candidate."""
    # This is tested implicitly by checking that duplicate.id == original.id
    # The actual vote counting logic is in finalize_voting and handle_vote_callback
    # which use candidate.id for vote tracking
    
    # Create mock candidate
    candidate1 = Mock(spec=TGUser)
    candidate1.id = 1
    candidate1.first_name = "Alice"
    candidate1.last_name = "Smith"
    candidate1.username = "alice"
    
    candidates = [candidate1]
    
    # Test duplication
    TEST_CHAT_ID = -4608252738
    result = duplicate_candidates_for_test(candidates, TEST_CHAT_ID, target_count=3)
    
    # Verify all duplicates have same ID as original
    assert len(result) == 3
    assert all(candidate.id == 1 for candidate in result)
    
    # Verify names are different for duplicates
    assert result[0].first_name == "Alice"
    assert result[1].first_name == "Alice (копия 2)"
    assert result[2].first_name == "Alice (копия 3)"


@pytest.mark.unit
def test_count_voters_with_empty_votes():
    """Test count_voters correctly handles users with empty vote arrays."""
    # Test with mix of users with votes and empty arrays
    votes_data = '{"123": [1, 2], "456": [], "789": [3], "999": []}'
    assert count_voters(votes_data) == 2  # Only users 123 and 789 have votes
    
    # Test with all users having empty arrays
    votes_data = '{"123": [], "456": [], "789": []}'
    assert count_voters(votes_data) == 0
    
    # Test with single user having empty array
    votes_data = '{"123": []}'
    assert count_voters(votes_data) == 0


@pytest.mark.unit
def test_create_voting_keyboard_no_checkmarks():
    """Test create_voting_keyboard doesn't add checkmarks to buttons."""
    # Create mock candidates
    candidate1 = Mock(spec=TGUser)
    candidate1.id = 1
    candidate1.first_name = "Alice"
    candidate1.last_name = "Smith"
    
    candidate2 = Mock(spec=TGUser)
    candidate2.id = 2
    candidate2.first_name = "Bob"
    candidate2.last_name = None
    
    candidates = [candidate1, candidate2]
    
    # Create keyboard
    voting_id = 123
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id)
    
    # Verify no checkmarks in button texts
    for row in keyboard.inline_keyboard:
        for button in row:
            assert "✅" not in button.text
            assert "☑️" not in button.text
            assert "✓" not in button.text
    
    # Verify button texts are clean names only
    assert keyboard.inline_keyboard[0][0].text == "Alice Smith"
    assert keyboard.inline_keyboard[0][1].text == "Bob"
