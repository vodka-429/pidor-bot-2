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
    result_winner, results = finalize_voting(mock_voting, mock_context)
    
    # Verify weighted votes and real votes calculation
    # Candidate 1: voted by user 1 (weight 5) and user 2 (weight 3) = 5 + 3 = 8 weighted, 2 votes
    # Candidate 2: voted by user 1 (weight 5) = 5 weighted, 1 vote
    # Candidate 3: voted by user 3 (weight 2) = 2 weighted, 1 vote
    assert results[1]['weighted'] == 8
    assert results[1]['votes'] == 2
    assert results[2]['weighted'] == 5
    assert results[2]['votes'] == 1
    assert results[3]['weighted'] == 2
    assert results[3]['votes'] == 1
    
    # Verify winner is candidate 1 (highest weighted votes)
    assert result_winner.id == 1
    
    # Note: GameResult creation is currently commented out in finalize_voting
    # So we don't verify db_session.add calls
    
    # Verify FinalVoting was updated
    assert mock_voting.ended_at is not None
    assert mock_voting.winner_id == 1
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.unit
def test_finalize_voting_no_votes(mock_context, sample_players, mocker):
    """Test finalize_voting handles case when nobody voted."""
    # Setup mock FinalVoting
    mock_voting = MagicMock()
    mock_voting.game_id = 1
    mock_voting.year = 2024
    mock_voting.missed_days_list = json.dumps([1, 2, 3])
    mock_voting.votes_data = json.dumps({})  # No votes
    
    # Setup player weights
    mock_weights_result = MagicMock()
    mock_weights_result.all.return_value = [(1, 5), (2, 3), (3, 2)]
    
    # Setup candidates query (all players who had wins)
    mock_candidates_result = MagicMock()
    mock_candidates_result.all.return_value = [1, 2, 3]
    
    # Mock random.choice to return deterministic result
    # Since random is imported inside finalize_voting, we need to patch it there
    import random
    mocker.patch.object(random, 'choice', return_value=2)
    
    # Setup winner query - winner will be candidate 2 (from mocked random.choice)
    winner = sample_players[1]
    winner.id = 2
    
    mock_context.db_session.exec.side_effect = [mock_weights_result, mock_candidates_result]
    mock_context.db_session.query.return_value.filter_by.return_value.one.return_value = winner
    
    # Execute
    result_winner, results = finalize_voting(mock_voting, mock_context)
    
    # Verify the mocked random winner was selected
    assert result_winner.id == 2
    
    # Verify results contains the winner with 0 votes
    assert 2 in results
    assert results[2]['weighted'] == 0
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
    
    # Setup winner query - max() will pick one deterministically
    winner = sample_players[0]
    winner.id = 1
    
    mock_context.db_session.exec.return_value = mock_weights_result
    mock_context.db_session.query.return_value.filter_by.return_value.one.return_value = winner
    
    # Execute
    result_winner, results = finalize_voting(mock_voting, mock_context)
    
    # Verify both candidates have equal weighted votes
    assert results[1]['weighted'] == 4
    assert results[2]['weighted'] == 4
    
    # Verify a winner was selected (max() picks one deterministically)
    assert result_winner.id in [1, 2]
    
    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.unit
def test_format_player_with_wins():
    """Test format_player_with_wins correctly formats player names with wins."""
    # Create mock player
    player = Mock(spec=TGUser)
    player.first_name = "Иван"
    player.last_name = "Иванов"
    
    # Test with 1 win (победа)
    result = format_player_with_wins(player, 1)
    assert result == "Иван Иванов (1 победа)"
    
    # Test with 2 wins (победы)
    result = format_player_with_wins(player, 2)
    assert result == "Иван Иванов (2 победы)"
    
    # Test with 5 wins (побед)
    result = format_player_with_wins(player, 5)
    assert result == "Иван Иванов (5 побед)"
    
    # Test with 11 wins (побед - exception for 11)
    result = format_player_with_wins(player, 11)
    assert result == "Иван Иванов (11 побед)"
    
    # Test with 21 wins (победа)
    result = format_player_with_wins(player, 21)
    assert result == "Иван Иванов (21 победа)"
    
    # Test with 22 wins (победы)
    result = format_player_with_wins(player, 22)
    assert result == "Иван Иванов (22 победы)"
    
    # Test player without last name
    player.last_name = None
    result = format_player_with_wins(player, 3)
    assert result == "Иван (3 победы)"


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
    assert "Алиса Смит \\(5 побед\\)" in result
    assert "Боб \\(3 победы\\)" in result
    assert "Чарли Браун \\(2 победы\\)" in result
    assert "Финальное голосование года" in result
    assert "Голосуйте мудро" in result


@pytest.mark.unit
def test_create_voting_keyboard_with_user_votes():
    """Test create_voting_keyboard shows checkmarks for voted candidates."""
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
    
    # User has voted for candidates 1 and 3
    user_votes = [1, 3]
    
    # Create keyboard
    voting_id = 123
    keyboard = create_voting_keyboard(candidates, voting_id=voting_id, votes_per_row=2, user_votes=user_votes)
    
    # Verify checkmarks are added to voted candidates
    assert keyboard.inline_keyboard[0][0].text == "✅ Alice Smith"  # Candidate 1 - voted
    assert keyboard.inline_keyboard[0][1].text == "Bob"  # Candidate 2 - not voted
    assert keyboard.inline_keyboard[1][0].text == "✅ Charlie Brown"  # Candidate 3 - voted
    
    # Verify callback_data is still correct
    assert keyboard.inline_keyboard[0][0].callback_data == "vote_123_1"
    assert keyboard.inline_keyboard[0][1].callback_data == "vote_123_2"
    assert keyboard.inline_keyboard[1][0].callback_data == "vote_123_3"
