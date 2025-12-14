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
    get_year_leaders,
    format_weights_message,
    format_voting_results,
    count_voters,
    calculate_max_votes,
    calculate_voting_params,
    duplicate_candidates_for_test,
    distribute_days_proportionally,
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
    # Используем Telegram ID как в handle_vote_callback
    votes_data = {
        "1001": [1, 2],  # User 1 (tg_id=1001) votes for candidates 1 and 2
        "1002": [1],     # User 2 (tg_id=1002) votes for candidate 1
        "1003": [3]      # User 3 (tg_id=1003) votes for candidate 3
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights (wins in the year)
    # User 1 has 5 wins, User 2 has 3 wins, User 3 has 2 wins
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 5), (2, 1002, 3), (3, 1003, 2)]

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
    # NEW LOGIC: auto votes are NOT counted in 'votes', only in 'auto_votes'
    # Candidate 1: voted by user 1 (weight 5, 2 votes) + voted by user 2 (weight 3, 1 vote) = 5/2 + 3 = 2.5 + 3.0 = 5.5 weighted, 2 manual votes
    # Candidate 2: voted by user 1 (weight 5, 2 votes) = 5/2 = 2.5 weighted, 1 manual vote
    # Candidate 3: voted by user 3 (weight 2, 1 vote) = 2.0 weighted, 1 manual vote
    assert results[1]['weighted'] == 5.5
    assert results[1]['votes'] == 2  # Only manual votes
    assert results[1]['auto_votes'] == 0  # No auto votes
    assert results[2]['weighted'] == 2.5
    assert results[2]['votes'] == 1  # Only manual votes
    assert results[2]['auto_votes'] == 0  # No auto votes
    assert results[3]['weighted'] == 2.0
    assert results[3]['votes'] == 1  # Only manual votes
    assert results[3]['auto_votes'] == 0  # No auto votes

    # Verify winner is candidate 1 (highest weighted votes)
    assert winner_id == 1
    assert winner_obj.id == 1

    # Note: GameResult creation is currently commented out in finalize_voting
    # So we don't verify db_session.add calls

    # Verify FinalVoting was updated
    assert mock_voting.ended_at is not None
    assert mock_voting.winner_id == 1

    # Verify commit was called (may be called multiple times for winners_data)
    assert mock_context.db_session.commit.called


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
    mock_weights_result.all.return_value = [(1, 1001, 5), (2, 1002, 3), (3, 1003, 2)]

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

    # Verify commit was called (may be called multiple times for winners_data)
    assert mock_context.db_session.commit.called


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
        "1001": [1],
        "1002": [2]
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 4), (2, 1002, 4)]

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
    assert results[1]['votes'] == 1  # Only manual votes
    assert results[1]['auto_votes'] == 0  # No auto votes
    assert results[2]['weighted'] == 4.0
    assert results[2]['votes'] == 1  # Only manual votes
    assert results[2]['auto_votes'] == 0  # No auto votes

    # Verify winners is a list
    assert isinstance(winners, list)
    assert len(winners) == 1  # Only 1 winner for 2 missed days
    winner_id, winner_obj = winners[0]
    assert winner_id in [1, 2]

    # Verify commit was called (may be called multiple times for winners_data)
    assert mock_context.db_session.commit.called


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
    assert "Алиса Смит \\(5 побед\\)" in result
    assert "Боб \\(3 победы\\)" in result
    assert "Чарли Браун \\(2 победы\\)" in result
    assert "Финальное голосование года" in result
    assert "Голосуйте мудро" in result


@pytest.mark.unit
def test_get_year_leaders_single():
    """Test get_year_leaders with single leader."""
    # Create mock players
    player1 = Mock(spec=DBUser)
    player1.first_name = "Alice"
    player1.last_name = "Smith"

    player2 = Mock(spec=DBUser)
    player2.first_name = "Bob"
    player2.last_name = None

    player3 = Mock(spec=DBUser)
    player3.first_name = "Charlie"
    player3.last_name = "Brown"

    # Setup player weights with single leader (Alice with 5 wins)
    player_weights = [
        (player1, 5),
        (player2, 3),
        (player3, 2)
    ]

    # Execute
    result = get_year_leaders(player_weights)

    # Verify only Alice is returned as leader
    assert len(result) == 1
    assert result[0] == (player1, 5)


@pytest.mark.unit
def test_get_year_leaders_multiple_with_same_max():
    """Test get_year_leaders with multiple leaders having same max wins."""
    # Create mock players
    player1 = Mock(spec=DBUser)
    player1.first_name = "Alice"
    player1.last_name = "Smith"

    player2 = Mock(spec=DBUser)
    player2.first_name = "Bob"
    player2.last_name = None

    player3 = Mock(spec=DBUser)
    player3.first_name = "Charlie"
    player3.last_name = "Brown"

    player4 = Mock(spec=DBUser)
    player4.first_name = "David"
    player4.last_name = "Wilson"

    # Setup player weights with multiple leaders (Alice and Bob with 5 wins each)
    player_weights = [
        (player1, 5),
        (player2, 5),
        (player3, 3),
        (player4, 2)
    ]

    # Execute
    result = get_year_leaders(player_weights)

    # Verify both Alice and Bob are returned as leaders
    assert len(result) == 2
    assert (player1, 5) in result
    assert (player2, 5) in result


@pytest.mark.unit
def test_get_year_leaders_all_equal():
    """Test get_year_leaders when all players have equal wins."""
    # Create mock players
    player1 = Mock(spec=DBUser)
    player1.first_name = "Alice"
    player1.last_name = "Smith"

    player2 = Mock(spec=DBUser)
    player2.first_name = "Bob"
    player2.last_name = None

    player3 = Mock(spec=DBUser)
    player3.first_name = "Charlie"
    player3.last_name = "Brown"

    # Setup player weights with all players having same wins
    player_weights = [
        (player1, 3),
        (player2, 3),
        (player3, 3)
    ]

    # Execute
    result = get_year_leaders(player_weights)

    # Verify all players are returned as leaders
    assert len(result) == 3
    assert (player1, 3) in result
    assert (player2, 3) in result
    assert (player3, 3) in result


@pytest.mark.unit
def test_get_year_leaders_empty_list():
    """Test get_year_leaders with empty player weights list."""
    # Execute
    result = get_year_leaders([])

    # Verify empty list is returned
    assert result == []




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

@pytest.mark.unit
def test_calculate_voting_params_test_chat_limit():
    """Test calculate_voting_params with test chat limit."""
    from bot.handlers.game.commands import TEST_CHAT_ID

    # Test with 15 missed days in test chat - should limit to 10
    effective_days, max_votes = calculate_voting_params(15, TEST_CHAT_ID)
    assert effective_days == 10
    assert max_votes == 5  # 10 days (even) → 10/2 = 5 votes

    # Test with regular chat - no limit, 15 is composite (3*5)
    effective_days, max_votes = calculate_voting_params(15, -123456789)
    assert effective_days == 15
    assert max_votes == 5  # 15/3 = 5 (15 is composite odd, smallest divisor is 3)


@pytest.mark.unit
def test_calculate_voting_params_regular_chat():
    """Test calculate_voting_params for regular chat without limit."""
    # Test various values without chat_id (no limit)
    effective_days, max_votes = calculate_voting_params(2)
    assert effective_days == 2
    assert max_votes == 1  # 2/2 = 1

    effective_days, max_votes = calculate_voting_params(4)
    assert effective_days == 4
    assert max_votes == 2  # 4/2 = 2

    effective_days, max_votes = calculate_voting_params(6)
    assert effective_days == 6
    assert max_votes == 3  # 6/2 = 3

    effective_days, max_votes = calculate_voting_params(9)
    assert effective_days == 9
    assert max_votes == 3  # 9/3 = 3 (composite odd)

    # Test with regular chat_id (not test chat)
    effective_days, max_votes = calculate_voting_params(8, -987654321)
    assert effective_days == 8
    assert max_votes == 4  # 8/2 = 4


@pytest.mark.unit
def test_calculate_voting_params_test_chat_under_limit():
    """Test calculate_voting_params with test chat when under limit."""
    from bot.handlers.game.commands import TEST_CHAT_ID

    # Test with 5 missed days in test chat - under limit, no change
    effective_days, max_votes = calculate_voting_params(5, TEST_CHAT_ID)
    assert effective_days == 5
    assert max_votes == 1  # 5 is prime → 1 vote

    # Test with exactly 10 days - at limit, no change
    effective_days, max_votes = calculate_voting_params(10, TEST_CHAT_ID)
    assert effective_days == 10
    assert max_votes == 5  # 10/2 = 5


@pytest.mark.unit
def test_calculate_max_votes_backward_compatibility():
    """Test calculate_max_votes backward compatibility wrapper."""
    from bot.handlers.game.commands import TEST_CHAT_ID

    # Test that calculate_max_votes returns only max_votes
    max_votes = calculate_max_votes(10)
    assert max_votes == 5
    assert isinstance(max_votes, int)

    # Test with test chat - should apply limit
    max_votes = calculate_max_votes(15, TEST_CHAT_ID)
    assert max_votes == 5  # Limited to 10 days → 10/2 = 5

    # Test with regular chat - no limit, 15 is composite (3*5)
    max_votes = calculate_max_votes(15, -123456789)
    assert max_votes == 5  # 15/3 = 5 (15 is composite odd, smallest divisor is 3)

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
        "1001": [1]  # User 1 (tg_id=1001) votes for candidate 1
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights: users 1, 2, 3 all have weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 5), (2, 1002, 3), (3, 1003, 2)]

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
    assert results[1]['auto_votes'] == 0
    assert results[2]['weighted'] == 3.0
    assert results[2]['votes'] == 0  # No manual votes
    assert results[2]['auto_votes'] == 2  # Only auto votes
    assert results[3]['weighted'] == 2.0
    assert results[3]['votes'] == 0  # No manual votes
    assert results[3]['auto_votes'] == 2  # Only auto votes

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
        "1001": [2],  # User 1 (tg_id=1001) votes for candidate 2
        "1002": [1]   # User 2 (tg_id=1002) votes for candidate 1
        # User 3 doesn't vote - should get auto vote for himself
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 3), (2, 1002, 4), (3, 1003, 6)]

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

    # Verify results with NEW LOGIC: auto votes NOT counted in 'votes'
    # Candidate 1: voted by user 2 (weight 4, 1 vote) = 4.0 weighted, 1 manual vote
    # Candidate 2: voted by user 1 (weight 3, 1 vote) = 3.0 weighted, 1 manual vote
    # Candidate 3: auto-voted by user 3 (weight 6, 1 vote) = 6.0 weighted, 0 manual votes, 1 auto vote
    assert results[1]['weighted'] == 4.0
    assert results[1]['votes'] == 1  # Only manual votes
    assert results[1]['auto_votes'] == 0  # No auto votes
    assert results[2]['weighted'] == 3.0
    assert results[2]['votes'] == 1  # Only manual votes
    assert results[2]['auto_votes'] == 0  # No auto votes
    assert results[3]['weighted'] == 6.0
    assert results[3]['votes'] == 0  # No manual votes
    assert results[3]['auto_votes'] == 1  # Only auto votes

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
    mock_weights_result.all.return_value = [(1, 1001, 2), (2, 1002, 4)]

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
    assert results[1]['votes'] == 0  # No manual votes
    assert results[1]['auto_votes'] == 3  # Only auto votes
    assert results[2]['weighted'] == 4.0
    assert results[2]['votes'] == 0  # No manual votes
    assert results[2]['auto_votes'] == 3  # Only auto votes

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


@pytest.mark.unit
def test_finalize_voting_auto_voted_flag_mixed_voting(mock_context, sample_players):
    """Test finalize_voting correctly sets auto_voted flag in mixed voting scenario."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4])
    mock_voting.missed_days_count = 4  # 4 дня → 2 выбора по формуле

    # Setup votes_data: mixed scenario
    # User 1 votes manually for candidates 2 and 3
    # User 2 votes manually for candidate 1
    # User 3 doesn't vote - should get auto vote for himself
    votes_data = {
        "1001": [2, 3],  # User 1 (tg_id=1001) votes for candidates 2 and 3
        "1002": [1]      # User 2 (tg_id=1002) votes for candidate 1
        # User 3 doesn't vote - should get auto vote for himself with 2 votes
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 6), (2, 1002, 4), (3, 1003, 8)]

    # Setup winner queries - need to mock for multiple winners
    winner1 = sample_players[0]
    winner1.id = 1
    winner2 = sample_players[1]
    winner2.id = 2
    winner3 = sample_players[2]
    winner3.id = 3

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
            elif id == 3:
                mock_filter_q.one.return_value = winner3
            else:
                mock_filter_q.one.return_value = winner3
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q

    mock_context.db_session.query.side_effect = query_side_effect

    # Execute with auto_vote enabled
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True)

    # Verify winners is a list
    assert isinstance(winners, list)
    assert len(winners) >= 1

    # Verify auto_voted flags for all candidates:
    # Candidate 1: voted by user 2 (manual voter) → auto_voted should be False (user 2 is in manual_voters)
    # But wait, auto_voted flag is for the CANDIDATE, not the voter!
    # Candidate 1 (user 1) voted manually → auto_voted = False (user 1 is in manual_voters)
    # Candidate 2 (user 2) voted manually → auto_voted = False (user 2 is in manual_voters)
    # Candidate 3 (user 3) didn't vote manually → auto_voted = True (user 3 is NOT in manual_voters)

    assert results[1]['auto_voted'] == False  # User 1 voted manually
    assert results[2]['auto_voted'] == False  # User 2 voted manually
    assert results[3]['auto_voted'] == True   # User 3 didn't vote manually (got auto vote)

    # Verify vote counts:
    # Candidate 1: voted by user 2 (weight 4, 1 vote) = 4.0 weighted, 1 manual vote
    # Candidate 2: voted by user 1 (weight 6, 2 votes) = 6/2 = 3.0 weighted, 1 manual vote
    # Candidate 3: voted by user 1 (weight 6, 2 votes) + auto-voted by user 3 (weight 8, 2 votes) = 6/2 + 8 = 3.0 + 8.0 = 11.0 weighted, 1 manual + 2 auto
    assert results[1]['weighted'] == 4.0
    assert results[1]['votes'] == 1
    assert results[1]['auto_votes'] == 0
    assert results[2]['weighted'] == 3.0  # Исправлено: пользователь 1 (weight 6) голосует за 2 кандидатов = 6/2 = 3.0
    assert results[2]['votes'] == 1
    assert results[2]['auto_votes'] == 0
    assert results[3]['weighted'] == 11.0
    assert results[3]['votes'] == 1  # Only manual votes
    assert results[3]['auto_votes'] == 2  # Auto votes tracked separately

    # Verify unique voters count
    assert results[1]['unique_voters'] == 1  # Only user 2
    assert results[2]['unique_voters'] == 1  # Only user 1
    assert results[3]['unique_voters'] == 2  # User 1 and user 3

    # User 3 should win with highest weighted score (11.0 > 4.0 > 3.0)
    winner_id, winner_obj = winners[0]
    assert winner_id == 3
    assert winner_obj.id == 3


@pytest.mark.unit
def test_finalize_voting_with_tg_id_mapping(mock_context, sample_players):
    """Test finalize_voting correctly maps Telegram IDs to database IDs."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3])
    mock_voting.missed_days_count = 3  # 3 дня → 1 выбор по формуле

    # Setup votes_data с Telegram ID (как в handle_vote_callback)
    # Пусть у sample_players[0] tg_id = 1001, sample_players[1] tg_id = 1002, sample_players[2] tg_id = 1003
    sample_players[0].tg_id = 1001
    sample_players[1].tg_id = 1002
    sample_players[2].tg_id = 1003

    votes_data = {
        "1001": [2],  # Пользователь с tg_id=1001 голосует за кандидата 2
        # Пользователь с tg_id=1002 не голосует
        "1003": [1]   # Пользователь с tg_id=1003 голосует за кандидата 1
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights с включением tg_id
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 5), (2, 1002, 3), (3, 1003, 2)]

    # Setup winner query
    winner = sample_players[1]  # Должен победить кандидат 2
    winner.id = 2

    # Мокаем запросы к базе данных
    mock_context.db_session.exec.return_value = mock_weights_result
    mock_context.db_session.query.return_value.filter_by.return_value.one.return_value = winner

    # Execute
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True)

    # Verify winners is a list
    assert isinstance(winners, list)
    assert len(winners) >= 1
    winner_id, winner_obj = winners[0]

    # Verify results with NEW LOGIC: auto votes NOT counted in 'votes'
    # Candidate 1: voted by user 3 (tg_id=1003, db_id=3, weight 2) = 2.0 weighted, 1 manual vote
    # Candidate 2: voted by user 1 (tg_id=1001, db_id=1, weight 5) + auto-voted by user 2 (tg_id=1002, db_id=2, weight 3) = 5.0 + 3.0 = 8.0 weighted, 1 manual + 1 auto
    # Candidate 3: не получил голосов

    assert results[1]['votes'] == 1  # Только пользователь 3 проголосовал за кандидата 1 (manual)
    assert results[1]['auto_votes'] == 0  # No auto votes
    assert results[2]['votes'] == 1  # Только пользователь 1 проголосовал за кандидата 2 (manual)
    assert results[2]['auto_votes'] == 1  # Автоголос от пользователя 2
    # Проверяем, что кандидат 3 отсутствует в результатах (не получил голосов)
    assert 3 not in results

    # Candidate 2 should win with highest weighted score (8.0 > 2.0)
    assert winner_id == 2
    assert winner_obj.id == 2


@pytest.mark.unit
def test_distribute_days_proportionally_equal_scores():
    """Test distribute_days_proportionally with equal scores."""
    # Create mock users
    user1 = Mock(spec=DBUser)
    user1.first_name = "Alice"
    user1.last_name = "Smith"

    user2 = Mock(spec=DBUser)
    user2.first_name = "Bob"
    user2.last_name = None

    user3 = Mock(spec=DBUser)
    user3.first_name = "Charlie"
    user3.last_name = "Brown"

    # Setup winners with equal scores
    winners_scores = [
        (1, user1, 10.0),
        (2, user2, 10.0),
        (3, user3, 10.0)
    ]

    total_days = 6

    # Execute
    result = distribute_days_proportionally(winners_scores, total_days)

    # Verify equal distribution (6 days / 3 winners = 2 days each)
    assert len(result) == 3
    assert result[0] == (1, user1, 2)
    assert result[1] == (2, user2, 2)
    assert result[2] == (3, user3, 2)

    # Verify sum equals total_days
    assert sum(days for _, _, days in result) == total_days


@pytest.mark.unit
def test_distribute_days_proportionally_different_scores():
    """Test distribute_days_proportionally with different scores."""
    # Create mock users
    user1 = Mock(spec=DBUser)
    user1.first_name = "Alice"
    user1.last_name = "Smith"

    user2 = Mock(spec=DBUser)
    user2.first_name = "Bob"
    user2.last_name = None

    user3 = Mock(spec=DBUser)
    user3.first_name = "Charlie"
    user3.last_name = "Brown"

    # Setup winners with different scores
    winners_scores = [
        (1, user1, 40.0),  # 40/60 = 66.7% → 4.0 days
        (2, user2, 15.0),  # 15/60 = 25.0% → 1.5 days
        (3, user3, 5.0)    # 5/60 = 8.3% → 0.5 days
    ]

    total_days = 6

    # Execute
    result = distribute_days_proportionally(winners_scores, total_days)

    # Verify proportional distribution
    assert len(result) == 3

    # Alice should get 4 days (66.7% of 6)
    assert result[0][0] == 1  # Alice is first (highest score)
    assert result[0][2] == 4

    # Bob should get 2 days (25% of 6 = 1.5, rounded up due to remainder)
    assert result[1][0] == 2  # Bob is second
    assert result[1][2] == 2

    # Charlie should get 0 days (8.3% of 6 = 0.5, rounded down)
    assert result[2][0] == 3  # Charlie is third
    assert result[2][2] == 0

    # Verify sum equals total_days
    assert sum(days for _, _, days in result) == total_days


@pytest.mark.unit
def test_distribute_days_proportionally_remainder():
    """Test distribute_days_proportionally with remainder distribution."""
    # Create mock users
    user1 = Mock(spec=DBUser)
    user1.first_name = "Alice"
    user1.last_name = "Smith"

    user2 = Mock(spec=DBUser)
    user2.first_name = "Bob"
    user2.last_name = None

    user3 = Mock(spec=DBUser)
    user3.first_name = "Charlie"
    user3.last_name = "Brown"

    # Setup winners with scores that create remainders
    winners_scores = [
        (1, user1, 33.3),  # 33.3/100 = 33.3% → 3.33 days
        (2, user2, 33.3),  # 33.3/100 = 33.3% → 3.33 days
        (3, user3, 33.4)   # 33.4/100 = 33.4% → 3.34 days
    ]

    total_days = 10

    # Execute
    result = distribute_days_proportionally(winners_scores, total_days)

    # Verify distribution with remainder
    assert len(result) == 3

    # All should get 3 days (floor of 3.33, 3.33, 3.34)
    # Remainder = 10 - (3+3+3) = 1
    # The one with highest fractional part (0.34) gets the extra day

    # Charlie should get 4 days (highest fractional part)
    assert result[0][0] == 3  # Charlie is first (highest fractional part)
    assert result[0][2] == 4

    # Alice should get 3 days
    assert result[1][0] == 1  # Alice is second
    assert result[1][2] == 3

    # Bob should get 3 days
    assert result[2][0] == 2  # Bob is third
    assert result[2][2] == 3

    # Verify sum equals total_days
    assert sum(days for _, _, days in result) == total_days


@pytest.mark.unit
def test_distribute_days_proportionally_sum_preserved():
    """Test that distribute_days_proportionally always preserves the sum."""
    # Create mock users
    user1 = Mock(spec=DBUser)
    user1.first_name = "Alice"
    user1.last_name = "Smith"

    user2 = Mock(spec=DBUser)
    user2.first_name = "Bob"
    user2.last_name = None

    # Test with various total_days values
    for total_days in [1, 3, 5, 7, 10, 13]:
        # Setup winners with any scores
        winners_scores = [
            (1, user1, 60.0),
            (2, user2, 40.0)
        ]

        # Execute
        result = distribute_days_proportionally(winners_scores, total_days)

        # Verify sum equals total_days
        assert sum(days for _, _, days in result) == total_days


@pytest.mark.unit
def test_distribute_days_proportionally_empty_list():
    """Test distribute_days_proportionally with empty winners list."""
    # Execute with empty list
    result = distribute_days_proportionally([], 5)

    # Verify empty result
    assert result == []


@pytest.mark.unit
def test_distribute_days_proportionally_zero_days():
    """Test distribute_days_proportionally with zero total days."""
    # Create mock users
    user1 = Mock(spec=DBUser)
    user1.first_name = "Alice"
    user1.last_name = "Smith"

    # Setup winners
    winners_scores = [
        (1, user1, 10.0)
    ]

    # Execute with zero days
    result = distribute_days_proportionally(winners_scores, 0)

    # Verify empty result
    assert result == []


@pytest.mark.unit
def test_distribute_days_proportionally_zero_scores():
    """Test distribute_days_proportionally with all zero scores."""
    # Create mock users
    user1 = Mock(spec=DBUser)
    user1.first_name = "Alice"
    user1.last_name = "Smith"

    user2 = Mock(spec=DBUser)
    user2.first_name = "Bob"
    user2.last_name = None

    user3 = Mock(spec=DBUser)
    user3.first_name = "Charlie"
    user3.last_name = "Brown"

    # Setup winners with zero scores
    winners_scores = [
        (1, user1, 0.0),
        (2, user2, 0.0),
        (3, user3, 0.0)
    ]

    total_days = 5

    # Execute
    result = distribute_days_proportionally(winners_scores, total_days)

    # Verify equal distribution (5 days / 3 winners = 1, 2, 2)
    assert len(result) == 3
    assert sum(days for _, _, days in result) == total_days

    # First winner gets 2 days (remainder distribution)
    assert result[0][2] == 2
    # Second winner gets 2 days (remainder distribution)
    assert result[1][2] == 2
    # Third winner gets 1 day
    assert result[2][2] == 1


@pytest.mark.unit
def test_create_voting_keyboard_with_single_exclusion():
    """Test create_voting_keyboard with single excluded player."""
    # Create mock candidates
    candidate1 = Mock(spec=TGUser)
    candidate1.id = 1
    candidate1.first_name = "Alice"
    candidate1.last_name = "Smith"

    candidate2 = Mock(spec=TGUser)
    candidate2.id = 2
    candidate2.first_name = "Bob"
    candidate2.last_name = None

    candidate3 = Mock(spec=TGUser)
    candidate3.id = 3
    candidate3.first_name = "Charlie"
    candidate3.last_name = "Brown"

    candidates = [candidate1, candidate2, candidate3]

    # Create keyboard with excluded player (Bob with ID 2)
    voting_id = 123
    excluded_players = [2]
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, excluded_players=excluded_players)

    # Verify structure: 2 candidates (Alice and Charlie) remain
    assert len(keyboard.inline_keyboard) == 1  # 1 row
    assert len(keyboard.inline_keyboard[0]) == 2  # 2 buttons in row

    # Verify button texts (Bob should be excluded)
    button_texts = [button.text for button in keyboard.inline_keyboard[0]]
    assert "Alice Smith" in button_texts
    assert "Charlie Brown" in button_texts
    assert "Bob" not in button_texts

    # Verify callback_data contains only remaining candidates
    callback_data_list = [button.callback_data for button in keyboard.inline_keyboard[0]]
    assert "vote_123_1" in callback_data_list  # Alice
    assert "vote_123_3" in callback_data_list  # Charlie
    assert "vote_123_2" not in callback_data_list  # Bob should be excluded


@pytest.mark.unit
def test_create_voting_keyboard_with_multiple_exclusions():
    """Test create_voting_keyboard with multiple excluded players."""
    # Create mock candidates
    candidate1 = Mock(spec=TGUser)
    candidate1.id = 1
    candidate1.first_name = "Alice"
    candidate1.last_name = "Smith"

    candidate2 = Mock(spec=TGUser)
    candidate2.id = 2
    candidate2.first_name = "Bob"
    candidate2.last_name = None

    candidate3 = Mock(spec=TGUser)
    candidate3.id = 3
    candidate3.first_name = "Charlie"
    candidate3.last_name = "Brown"

    candidate4 = Mock(spec=TGUser)
    candidate4.id = 4
    candidate4.first_name = "David"
    candidate4.last_name = "Wilson"

    candidates = [candidate1, candidate2, candidate3, candidate4]

    # Create keyboard with multiple excluded players (Bob and David)
    voting_id = 456
    excluded_players = [2, 4]
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, excluded_players=excluded_players)

    # Verify structure: 2 candidates (Alice and Charlie) remain
    assert len(keyboard.inline_keyboard) == 1  # 1 row
    assert len(keyboard.inline_keyboard[0]) == 2  # 2 buttons in row

    # Verify button texts (Bob and David should be excluded)
    button_texts = [button.text for button in keyboard.inline_keyboard[0]]
    assert "Alice Smith" in button_texts
    assert "Charlie Brown" in button_texts
    assert "Bob" not in button_texts
    assert "David Wilson" not in button_texts

    # Verify callback_data contains only remaining candidates
    callback_data_list = [button.callback_data for button in keyboard.inline_keyboard[0]]
    assert "vote_456_1" in callback_data_list  # Alice
    assert "vote_456_3" in callback_data_list  # Charlie
    assert "vote_456_2" not in callback_data_list  # Bob should be excluded
    assert "vote_456_4" not in callback_data_list  # David should be excluded


@pytest.mark.unit
def test_create_voting_keyboard_exclude_all_but_one():
    """Test create_voting_keyboard with all but one candidate excluded."""
    # Create mock candidates
    candidate1 = Mock(spec=TGUser)
    candidate1.id = 1
    candidate1.first_name = "Alice"
    candidate1.last_name = "Smith"

    candidate2 = Mock(spec=TGUser)
    candidate2.id = 2
    candidate2.first_name = "Bob"
    candidate2.last_name = None

    candidate3 = Mock(spec=TGUser)
    candidate3.id = 3
    candidate3.first_name = "Charlie"
    candidate3.last_name = "Brown"

    candidates = [candidate1, candidate2, candidate3]

    # Create keyboard excluding all but Alice
    voting_id = 789
    excluded_players = [2, 3]
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, excluded_players=excluded_players)

    # Verify structure: only 1 candidate (Alice) remains
    assert len(keyboard.inline_keyboard) == 1  # 1 row
    assert len(keyboard.inline_keyboard[0]) == 1  # 1 button in row

    # Verify button text (only Alice should remain)
    assert keyboard.inline_keyboard[0][0].text == "Alice Smith"

    # Verify callback_data contains only Alice
    assert keyboard.inline_keyboard[0][0].callback_data == "vote_789_1"


@pytest.mark.unit
def test_create_voting_keyboard_with_exclusions_and_player_wins():
    """Test create_voting_keyboard with both exclusions and player_wins."""
    # Create mock candidates
    candidate1 = Mock(spec=TGUser)
    candidate1.id = 1
    candidate1.first_name = "Alice"
    candidate1.last_name = "Smith"

    candidate2 = Mock(spec=TGUser)
    candidate2.id = 2
    candidate2.first_name = "Bob"
    candidate2.last_name = None

    candidate3 = Mock(spec=TGUser)
    candidate3.id = 3
    candidate3.first_name = "Charlie"
    candidate3.last_name = "Brown"

    candidates = [candidate1, candidate2, candidate3]

    # Create keyboard with excluded player (Bob) and player_wins
    voting_id = 123
    excluded_players = [2]
    player_wins = {1: 5, 3: 2}  # Alice has 5 wins, Charlie has 2 wins
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, excluded_players=excluded_players, player_wins=player_wins)

    # Verify structure: 2 candidates (Alice and Charlie) remain
    assert len(keyboard.inline_keyboard) == 1  # 1 row
    assert len(keyboard.inline_keyboard[0]) == 2  # 2 buttons in row

    # Verify button texts with wins (Bob should be excluded)
    button_texts = [button.text for button in keyboard.inline_keyboard[0]]
    assert "Alice Smith (5)" in button_texts
    assert "Charlie Brown (2)" in button_texts
    assert "Bob" not in button_texts

    # Verify callback_data contains only remaining candidates
    callback_data_list = [button.callback_data for button in keyboard.inline_keyboard[0]]
    assert "vote_123_1" in callback_data_list  # Alice
    assert "vote_123_3" in callback_data_list  # Charlie
    assert "vote_123_2" not in callback_data_list  # Bob should be excluded


@pytest.mark.unit
def test_create_voting_keyboard_with_empty_exclusions():
    """Test create_voting_keyboard with empty excluded_players list."""
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

    # Create keyboard with empty excluded_players list
    voting_id = 123
    excluded_players = []
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, excluded_players=excluded_players)

    # Verify structure: all candidates remain
    assert len(keyboard.inline_keyboard) == 1  # 1 row
    assert len(keyboard.inline_keyboard[0]) == 2  # 2 buttons in row

    # Verify button texts (all candidates should be present)
    button_texts = [button.text for button in keyboard.inline_keyboard[0]]
    assert "Alice Smith" in button_texts
    assert "Bob" in button_texts

    # Verify callback_data contains all candidates
    callback_data_list = [button.callback_data for button in keyboard.inline_keyboard[0]]
    assert "vote_123_1" in callback_data_list  # Alice
    assert "vote_123_2" in callback_data_list  # Bob


@pytest.mark.unit
def test_create_voting_keyboard_with_none_exclusions():
    """Test create_voting_keyboard with None excluded_players."""
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

    # Create keyboard with None excluded_players
    voting_id = 123
    excluded_players = None
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, excluded_players=excluded_players)

    # Verify structure: all candidates remain
    assert len(keyboard.inline_keyboard) == 1  # 1 row
    assert len(keyboard.inline_keyboard[0]) == 2  # 2 buttons in row

    # Verify button texts (all candidates should be present)
    button_texts = [button.text for button in keyboard.inline_keyboard[0]]
    assert "Alice Smith" in button_texts
    assert "Bob" in button_texts

    # Verify callback_data contains all candidates
    callback_data_list = [button.callback_data for button in keyboard.inline_keyboard[0]]
    assert "vote_123_1" in callback_data_list  # Alice
    assert "vote_123_2" in callback_data_list  # Bob


@pytest.mark.unit
def test_format_weights_message_with_single_exclusion():
    """Test format_weights_message with single excluded leader."""
    # Create mock players
    player1 = Mock(spec=DBUser)
    player1.first_name = "Алиса"
    player1.last_name = "Смит"

    player2 = Mock(spec=DBUser)
    player2.first_name = "Боб"
    player2.last_name = None

    player3 = Mock(spec=DBUser)
    player3.first_name = "Чарли"
    player3.last_name = "Браун"

    # Setup player weights
    player_weights = [
        (player1, 5),
        (player2, 3),
        (player3, 2)
    ]

    # Setup excluded leader (Алиса with 5 wins)
    excluded_leaders = [(player1, 5)]

    # Execute
    result = format_weights_message(player_weights, missed_count=7, excluded_leaders=excluded_leaders)

    # Verify message contains expected elements
    assert "7" in result  # missed days count
    assert "Алиса Смит \\(5 побед\\)" in result  # player weights
    assert "Боб \\(3 победы\\)" in result
    assert "Чарли Браун \\(2 победы\\)" in result
    assert "❌ Алиса Смит НЕ УЧАСТВУЕТ \\(лидер года\\)" in result  # excluded leader info
    assert "Финальное голосование года" in result
    assert "Голосуйте мудро" in result


@pytest.mark.unit
def test_format_weights_message_with_multiple_exclusions():
    """Test format_weights_message with multiple excluded leaders."""
    # Create mock players
    player1 = Mock(spec=DBUser)
    player1.first_name = "Алиса"
    player1.last_name = "Смит"

    player2 = Mock(spec=DBUser)
    player2.first_name = "Боб"
    player2.last_name = None

    player3 = Mock(spec=DBUser)
    player3.first_name = "Чарли"
    player3.last_name = "Браун"

    player4 = Mock(spec=DBUser)
    player4.first_name = "Дэвид"
    player4.last_name = "Уилсон"

    # Setup player weights
    player_weights = [
        (player1, 5),
        (player2, 5),
        (player3, 3),
        (player4, 2)
    ]

    # Setup excluded leaders (Алиса and Боб with 5 wins each)
    excluded_leaders = [(player1, 5), (player2, 5)]

    # Execute
    result = format_weights_message(player_weights, missed_count=7, excluded_leaders=excluded_leaders)

    # Verify message contains expected elements
    assert "7" in result  # missed days count
    assert "Алиса Смит \\(5 побед\\)" in result  # player weights
    assert "Боб \\(5 побед\\)" in result
    assert "Чарли Браун \\(3 победы\\)" in result
    assert "Дэвид Уилсон \\(2 победы\\)" in result
    assert "❌ Алиса Смит НЕ УЧАСТВУЕТ \\(лидер года\\)" in result  # excluded leader info
    assert "❌ Боб НЕ УЧАСТВУЕТ \\(лидер года\\)" in result  # excluded leader info
    assert "Финальное голосование года" in result
    assert "Голосуйте мудро" in result


@pytest.mark.unit
def test_format_weights_message_with_no_exclusions():
    """Test format_weights_message without excluded leaders (original behavior)."""
    # Create mock players
    player1 = Mock(spec=DBUser)
    player1.first_name = "Алиса"
    player1.last_name = "Смит"

    player2 = Mock(spec=DBUser)
    player2.first_name = "Боб"
    player2.last_name = None

    # Setup player weights
    player_weights = [
        (player1, 5),
        (player2, 3)
    ]

    # Execute without excluded leaders
    result = format_weights_message(player_weights, missed_count=7)

    # Verify message contains expected elements
    assert "7" in result  # missed days count
    assert "Алиса Смит \\(5 побед\\)" in result  # player weights
    assert "Боб \\(3 победы\\)" in result
    assert "❌" not in result  # No exclusion markers
    assert "исключен" not in result  # No exclusion text
    assert "Финальное голосование года" in result
    assert "Голосуйте мудро" in result


@pytest.mark.unit
def test_format_weights_message_with_empty_exclusions():
    """Test format_weights_message with empty excluded leaders list."""
    # Create mock players
    player1 = Mock(spec=DBUser)
    player1.first_name = "Алиса"
    player1.last_name = "Смит"

    player2 = Mock(spec=DBUser)
    player2.first_name = "Боб"
    player2.last_name = None

    # Setup player weights
    player_weights = [
        (player1, 5),
        (player2, 3)
    ]

    # Execute with empty excluded leaders list
    result = format_weights_message(player_weights, missed_count=7, excluded_leaders=[])

    # Verify message contains expected elements
    assert "7" in result  # missed days count
    assert "Алиса Смит \\(5 побед\\)" in result  # player weights
    assert "Боб \\(3 победы\\)" in result
    assert "❌" not in result  # No exclusion markers
    assert "исключен" not in result  # No exclusion text
    assert "Финальное голосование года" in result
    assert "Голосуйте мудро" in result


@pytest.mark.unit
def test_finalize_voting_with_single_exclusion(mock_context, sample_players):
    """Test finalize_voting with single excluded leader."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4])
    mock_voting.missed_days_count = 4  # 4 дня → 2 выбора

    # Setup votes_data: all users vote
    # User 1 (leader, excluded) votes for candidate 2
    # User 2 votes for candidate 3
    # User 3 votes for candidate 2
    votes_data = {
        "1001": [2],  # User 1 (tg_id=1001, leader) votes for candidate 2
        "1002": [3],  # User 2 (tg_id=1002) votes for candidate 3
        "1003": [2]   # User 3 (tg_id=1003) votes for candidate 2
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights: User 1 is leader with 10 wins
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 10), (2, 1002, 5), (3, 1003, 3)]

    # Setup winner queries
    winner2 = sample_players[1]
    winner2.id = 2
    winner3 = sample_players[2]
    winner3.id = 3

    mock_context.db_session.exec.return_value = mock_weights_result

    # Mock query to return different winners based on filter_by call
    def query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def filter_by_side_effect(id=None):
            mock_filter_q = MagicMock()
            if id == 2:
                mock_filter_q.one.return_value = winner2
            elif id == 3:
                mock_filter_q.one.return_value = winner3
            else:
                mock_filter_q.one.return_value = winner2
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q

    mock_context.db_session.query.side_effect = query_side_effect

    # Execute with excluded leader (User 1)
    excluded_player_ids = [1]
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True, excluded_player_ids=excluded_player_ids)

    # Verify winners list
    assert isinstance(winners, list)
    assert len(winners) >= 1
    winner_id, winner_obj = winners[0]

    # Verify User 1 (excluded leader) is NOT in winners
    winner_ids = [wid for wid, _ in winners]
    assert 1 not in winner_ids

    # Verify results:
    # Candidate 2: voted by user 1 (weight 10, 1 vote) + voted by user 3 (weight 3, 1 vote) = 10.0 + 3.0 = 13.0 weighted
    # Candidate 3: voted by user 2 (weight 5, 1 vote) = 5.0 weighted
    assert results[2]['weighted'] == 13.0
    assert results[2]['votes'] == 2
    assert results[3]['weighted'] == 5.0
    assert results[3]['votes'] == 1

    # Candidate 2 should win (highest weighted score among non-excluded)
    assert winner_id == 2
    assert winner_obj.id == 2


@pytest.mark.unit
def test_finalize_voting_with_multiple_exclusions(mock_context, sample_players):
    """Test finalize_voting with multiple excluded leaders."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3, 4])
    mock_voting.missed_days_count = 4  # 4 дня → 2 выбора

    # Setup votes_data: all users vote
    # User 1 (leader, excluded) votes for candidate 3
    # User 2 (leader, excluded) votes for candidate 3
    # User 3 votes for candidate 4
    # User 4 votes for candidate 3
    votes_data = {
        "1001": [3],  # User 1 (tg_id=1001, leader) votes for candidate 3
        "1002": [3],  # User 2 (tg_id=1002, leader) votes for candidate 3
        "1003": [4],  # User 3 (tg_id=1003) votes for candidate 4
        "1004": [3]   # User 4 (tg_id=1004) votes for candidate 3
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights: Users 1 and 2 are leaders with 10 wins each
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 10), (2, 1002, 10), (3, 1003, 5), (4, 1004, 3)]

    # Setup winner queries
    winner3 = sample_players[2]
    winner3.id = 3
    winner4 = Mock(spec=sample_players[0].__class__)
    winner4.id = 4

    mock_context.db_session.exec.return_value = mock_weights_result

    # Mock query to return different winners based on filter_by call
    def query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def filter_by_side_effect(id=None):
            mock_filter_q = MagicMock()
            if id == 3:
                mock_filter_q.one.return_value = winner3
            elif id == 4:
                mock_filter_q.one.return_value = winner4
            else:
                mock_filter_q.one.return_value = winner3
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q

    mock_context.db_session.query.side_effect = query_side_effect

    # Execute with multiple excluded leaders (Users 1 and 2)
    excluded_player_ids = [1, 2]
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True, excluded_player_ids=excluded_player_ids)

    # Verify winners list
    assert isinstance(winners, list)
    assert len(winners) >= 1

    # Verify Users 1 and 2 (excluded leaders) are NOT in winners
    winner_ids = [wid for wid, _ in winners]
    assert 1 not in winner_ids
    assert 2 not in winner_ids

    # Verify results:
    # Candidate 3: voted by user 1 (weight 10) + user 2 (weight 10) + user 4 (weight 3) = 23.0 weighted
    # Candidate 4: voted by user 3 (weight 5) = 5.0 weighted
    assert results[3]['weighted'] == 23.0
    assert results[3]['votes'] == 3
    assert results[4]['weighted'] == 5.0
    assert results[4]['votes'] == 1

    # Candidate 3 should win (highest weighted score among non-excluded)
    winner_id, winner_obj = winners[0]
    assert winner_id == 3
    assert winner_obj.id == 3


@pytest.mark.unit
def test_finalize_voting_excluded_leaders_can_vote(mock_context, sample_players):
    """Test that excluded leaders can vote and their votes count with full weight."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3])
    mock_voting.missed_days_count = 3  # 3 дня → 1 выбор

    # Setup votes_data: excluded leader votes for another candidate
    # User 1 (leader, excluded) votes for candidate 2
    # User 2 votes for candidate 3
    votes_data = {
        "1001": [2],  # User 1 (tg_id=1001, leader) votes for candidate 2
        "1002": [3]   # User 2 (tg_id=1002) votes for candidate 3
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights: User 1 is leader with 15 wins
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 15), (2, 1002, 5), (3, 1003, 3)]

    # Setup winner queries
    winner2 = sample_players[1]
    winner2.id = 2
    winner3 = sample_players[2]
    winner3.id = 3

    mock_context.db_session.exec.return_value = mock_weights_result

    # Mock query to return different winners based on filter_by call
    def query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def filter_by_side_effect(id=None):
            mock_filter_q = MagicMock()
            if id == 2:
                mock_filter_q.one.return_value = winner2
            elif id == 3:
                mock_filter_q.one.return_value = winner3
            else:
                mock_filter_q.one.return_value = winner2
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q

    mock_context.db_session.query.side_effect = query_side_effect

    # Execute with excluded leader (User 1)
    excluded_player_ids = [1]
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True, excluded_player_ids=excluded_player_ids)

    # Verify excluded leader's vote counted with FULL weight
    # Candidate 2: voted by user 1 (weight 15, excluded but vote counts) = 15.0 weighted
    # Candidate 3: voted by user 2 (weight 5) + auto-voted by user 3 (weight 3) = 8.0 weighted
    assert results[2]['weighted'] == 15.0
    assert results[2]['votes'] == 1
    assert results[3]['weighted'] == 8.0

    # Candidate 2 should win (highest weighted score, even though voted by excluded leader)
    winner_id, winner_obj = winners[0]
    assert winner_id == 2
    assert winner_obj.id == 2


@pytest.mark.unit
def test_finalize_voting_excluded_leaders_cannot_win(mock_context, sample_players):
    """Test that excluded leaders cannot win even with highest votes."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3])
    mock_voting.missed_days_count = 3  # 3 дня → 1 выбор

    # Setup votes_data: everyone votes for the excluded leader
    # User 1 (leader, excluded) - doesn't vote, gets auto-vote for himself
    # User 2 votes for candidate 1 (excluded leader)
    # User 3 votes for candidate 1 (excluded leader)
    votes_data = {
        "1002": [1],  # User 2 (tg_id=1002) votes for candidate 1 (excluded)
        "1003": [1]   # User 3 (tg_id=1003) votes for candidate 1 (excluded)
    }
    mock_voting.votes_data = json.dumps(votes_data)

    # Setup player weights: User 1 is leader with 20 wins
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 1001, 20), (2, 1002, 5), (3, 1003, 3)]

    # Setup candidates result for _select_random_winners (только ID, не кортежи)
    mock_candidates_result = MagicMock()
    mock_candidates_result.all.return_value = [1, 2, 3]

    # Setup winner queries
    winner2 = sample_players[1]
    winner2.id = 2
    winner3 = sample_players[2]
    winner3.id = 3

    # Мокаем exec для возврата разных результатов: сначала веса, потом кандидаты для random selection
    mock_context.db_session.exec.side_effect = [mock_weights_result, mock_candidates_result]

    # Mock query to return different winners based on filter_by call
    def query_side_effect(*args, **kwargs):
        mock_q = MagicMock()
        def filter_by_side_effect(id=None):
            mock_filter_q = MagicMock()
            if id == 2:
                mock_filter_q.one.return_value = winner2
            elif id == 3:
                mock_filter_q.one.return_value = winner3
            else:
                mock_filter_q.one.return_value = winner2
            return mock_filter_q
        mock_q.filter_by.side_effect = filter_by_side_effect
        return mock_q

    mock_context.db_session.query.side_effect = query_side_effect

    # Execute with excluded leader (User 1)
    excluded_player_ids = [1]
    winners, results = finalize_voting(mock_voting, mock_context, auto_vote_for_non_voters=True, excluded_player_ids=excluded_player_ids)

    # Verify results:
    # Candidate 1 (excluded): voted by user 2 (weight 5) + user 3 (weight 3) = 8.0 weighted
    # Note: User 1 (excluded leader) doesn't get auto-vote even though they didn't vote manually
    # Candidate 2: no votes, 0.0 weighted
    # Candidate 3: no votes, 0.0 weighted
    assert results[1]['weighted'] == 8.0
    assert results[1]['votes'] == 2
    assert results[1]['auto_votes'] == 0

    # Verify User 1 (excluded leader) is NOT in winners despite highest votes
    winner_ids = [wid for wid, _ in winners]
    assert 1 not in winner_ids

    # One of the non-excluded candidates should win (User 2 or 3)
    # Since they have 0 votes, it should be random selection from eligible candidates
    winner_id, winner_obj = winners[0]
    assert winner_id in [2, 3]


@pytest.mark.unit
def test_format_voting_results_with_percentages():
    """Test format_voting_results displays percentages correctly."""
    # Create mock winners
    winner1 = Mock(spec=DBUser)
    winner1.id = 1
    winner1.first_name = "Alice"
    winner1.last_name = "Smith"
    winner1.full_username.return_value = "Alice Smith"

    winner2 = Mock(spec=DBUser)
    winner2.id = 2
    winner2.first_name = "Bob"
    winner2.last_name = None
    winner2.full_username.return_value = "Bob"

    winners = [(1, winner1), (2, winner2)]

    # Create mock results with weighted scores
    results = {
        1: {
            'weighted': 23.5,
            'votes': 5,
            'auto_votes': 0,
            'auto_voted': False
        },
        2: {
            'weighted': 22.5,
            'votes': 6,
            'auto_votes': 0,
            'auto_voted': False
        }
    }

    # Create mock db_session
    mock_db_session = Mock()
    mock_db_session.query.return_value.filter_by.return_value.one.side_effect = [
        winner1,  # For candidate 1
        winner2   # For candidate 2
    ]

    # Execute
    winners_text, voting_results_text, days_distribution_text = format_voting_results(
        winners, results, missed_days_count=8, db_session=mock_db_session
    )

    # Verify winners text
    assert winners_text == "Alice Smith, Bob"

    # Verify voting results text contains weighted scores (with escaped dots)
    assert "Alice Smith" in voting_results_text
    assert "Bob" in voting_results_text
    assert "23\\.5" in voting_results_text  # Dots are escaped in Markdown V2
    assert "22\\.5" in voting_results_text  # Dots are escaped in Markdown V2

    # Verify days distribution text contains percentages
    assert "Alice Smith" in days_distribution_text
    assert "Bob" in days_distribution_text
    assert "51\\.1%" in days_distribution_text  # 23.5 / (23.5 + 22.5) = 51.1%
    assert "48\\.9%" in days_distribution_text  # 22.5 / (23.5 + 22.5) = 48.9%
    assert "от общих очков" in days_distribution_text


@pytest.mark.unit
def test_format_voting_results_percentage_sum():
    """Test that percentages in format_voting_results sum to approximately 100%."""
    # Create mock winners
    winner1 = Mock(spec=DBUser)
    winner1.id = 1
    winner1.first_name = "Alice"
    winner1.last_name = "Smith"
    winner1.full_username.return_value = "Alice Smith"

    winner2 = Mock(spec=DBUser)
    winner2.id = 2
    winner2.first_name = "Bob"
    winner2.last_name = None
    winner2.full_username.return_value = "Bob"

    winner3 = Mock(spec=DBUser)
    winner3.id = 3
    winner3.first_name = "Charlie"
    winner3.last_name = "Brown"
    winner3.full_username.return_value = "Charlie Brown"

    winners = [(1, winner1), (2, winner2), (3, winner3)]

    # Create mock results with weighted scores
    results = {
        1: {
            'weighted': 40.0,
            'votes': 5,
            'auto_votes': 0,
            'auto_voted': False
        },
        2: {
            'weighted': 30.0,
            'votes': 3,
            'auto_votes': 0,
            'auto_voted': False
        },
        3: {
            'weighted': 30.0,
            'votes': 2,
            'auto_votes': 0,
            'auto_voted': False
        }
    }

    # Create mock db_session
    mock_db_session = Mock()
    mock_db_session.query.return_value.filter_by.return_value.one.side_effect = [
        winner1,  # For candidate 1
        winner2,  # For candidate 2
        winner3   # For candidate 3
    ]

    # Execute
    winners_text, voting_results_text, days_distribution_text = format_voting_results(
        winners, results, missed_days_count=10, db_session=mock_db_session
    )

    # Debug output to see what's in days_distribution_text
    print(f"DEBUG: days_distribution_text = '{days_distribution_text}'")

    # Extract percentages from days_distribution_text
    import re
    # Pattern to match percentages with or without escaped dots
    percentage_pattern = r'(\d+\\?\.\d+)%'
    percentages = re.findall(percentage_pattern, days_distribution_text)

    # Debug output to see what percentages were found
    print(f"DEBUG: percentages found = {percentages}")

    # Remove backslashes from percentages for proper conversion to float
    cleaned_percentages = [p.replace('\\', '') for p in percentages]
    print(f"DEBUG: cleaned percentages = {cleaned_percentages}")

    # Convert to float and sum
    percentage_sum = sum(float(p) for p in cleaned_percentages)

    # Verify sum is approximately 100% (allowing for rounding errors)
    assert 99.0 <= percentage_sum <= 101.0, f"Percentage sum {percentage_sum}% is not close to 100%"

    # Verify individual percentages are correct (with escaped dots for Markdown V2)
    assert "40\\.0%" in days_distribution_text  # 40.0 / 100.0 = 40.0%
    assert "30\\.0%" in days_distribution_text  # 30.0 / 100.0 = 30.0% (appears twice for Bob and Charlie)



@pytest.mark.unit
def test_format_voting_rules_message(sample_players):
    """Test format_voting_rules_message creates correct informational message."""
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

    # Setup excluded leaders
    excluded_leaders = [(sample_players[0], 5)]

    # Execute
    from bot.handlers.game.voting_helpers import format_voting_rules_message
    result = format_voting_rules_message(
        player_weights,
        missed_count=7,
        max_votes=1,
        excluded_leaders=excluded_leaders
    )

    # Verify message contains expected elements
    assert "Финальное голосование года" in result
    assert "7" in result  # missed days count
    assert "Алиса Смит \\(5 побед\\)" in result  # player weights
    assert "Боб \\(3 победы\\)" in result
    assert "Чарли Браун \\(2 победы\\)" in result
    assert "❌ Алиса Смит НЕ УЧАСТВУЕТ \\(лидер года\\)" in result  # excluded leader
    assert "Максимум *1*" in result  # max votes info
    assert "24 часа" in result  # duration info
    assert "Запустить голосование можно 29 или 30 декабря" in result  # date info

    # Verify proper MarkdownV2 escaping
    assert "\\(" in result  # parentheses escaped
    assert "\\)" in result
    assert "\\-" in result  # hyphens escaped
