"""Tests for coin service functionality."""
import pytest
from unittest.mock import MagicMock, Mock
from datetime import datetime

from bot.handlers.game.coin_service import (
    add_coins,
    get_balance,
    get_leaderboard,
    get_leaderboard_by_year
)
from bot.app.models import PidorCoinTransaction, TGUser


@pytest.mark.unit
def test_add_coins_creates_transaction(mock_db_session):
    """Test add_coins creates a new transaction record."""
    # Setup
    game_id = 1
    user_id = 1
    amount = 1
    year = 2024
    reason = "pidor_win"

    # Mock the transaction creation
    mock_transaction = MagicMock()
    mock_db_session.add = MagicMock()
    mock_db_session.refresh = MagicMock()

    # Execute
    result = add_coins(mock_db_session, game_id, user_id, amount, year, reason)

    # Verify transaction was created with correct parameters
    mock_db_session.add.assert_called_once()
    added_transaction = mock_db_session.add.call_args[0][0]

    assert isinstance(added_transaction, PidorCoinTransaction)
    assert added_transaction.game_id == game_id
    assert added_transaction.user_id == user_id
    assert added_transaction.amount == amount
    assert added_transaction.year == year
    assert added_transaction.reason == reason
    assert added_transaction.created_at is not None

    # Verify commit and refresh were called
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(added_transaction)

    # Verify the function returns the transaction
    assert result == added_transaction


@pytest.mark.unit
def test_add_coins_saves_year_and_reason(mock_db_session):
    """Test add_coins correctly saves year and reason parameters."""
    # Setup
    game_id = 1
    user_id = 1
    amount = 1
    year = 2023
    reason = "bonus"

    # Execute
    result = add_coins(mock_db_session, game_id, user_id, amount, year, reason)

    # Verify transaction has correct year and reason
    mock_db_session.add.assert_called_once()
    added_transaction = mock_db_session.add.call_args[0][0]

    assert added_transaction.year == year
    assert added_transaction.reason == reason


@pytest.mark.unit
def test_get_balance_sums_all_transactions(mock_db_session):
    """Test get_balance returns sum of all transactions for user."""
    # Setup
    game_id = 1
    user_id = 1
    expected_balance = 7  # 1 + 3 + 3 = 7

    # Mock exec result
    mock_result = MagicMock()
    mock_result.first.return_value = (expected_balance,)  # Возвращаем кортеж как в реальном запросе

    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_balance(mock_db_session, game_id, user_id)

    # Verify exec was called
    mock_db_session.exec.assert_called_once()

    # Verify correct balance is returned
    assert result == expected_balance


@pytest.mark.unit
def test_get_balance_zero_when_no_transactions(mock_db_session):
    """Test get_balance returns 0 when user has no transactions."""
    # Setup
    game_id = 1
    user_id = 1

    # Mock exec returning None (no transactions)
    mock_result = MagicMock()
    mock_result.first.return_value = None

    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_balance(mock_db_session, game_id, user_id)

    # Verify 0 is returned for no transactions
    assert result == 0


@pytest.mark.unit
def test_get_balance_zero_when_none_sum(mock_db_session):
    """Test get_balance returns 0 when sum is None."""
    # Setup
    game_id = 1
    user_id = 1

    # Mock exec returning None in the first element
    mock_result = MagicMock()
    mock_result.first.return_value = (None,)

    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_balance(mock_db_session, game_id, user_id)

    # Verify 0 is returned for None sum
    assert result == 0


@pytest.mark.unit
def test_get_leaderboard_returns_top_users(mock_db_session, sample_players):
    """Test get_leaderboard returns top users by total coins."""
    # Setup
    game_id = 1
    limit = 3

    # Mock exec result with user balances
    mock_result = MagicMock()
    mock_result.all.return_value = [
        (sample_players[0], 15),  # Player 1 with 15 coins
        (sample_players[1], 10),  # Player 2 with 10 coins
        (sample_players[2], 5)    # Player 3 with 5 coins
    ]

    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_leaderboard(mock_db_session, game_id, limit)

    # Verify exec was called
    mock_db_session.exec.assert_called_once()

    # Verify correct leaderboard is returned
    assert len(result) == 3
    assert result[0] == (sample_players[0], 15)
    assert result[1] == (sample_players[1], 10)
    assert result[2] == (sample_players[2], 5)


@pytest.mark.unit
def test_get_leaderboard_empty_when_no_transactions(mock_db_session):
    """Test get_leaderboard returns empty list when no transactions."""
    # Setup
    game_id = 1
    limit = 10

    # Mock exec returning empty result
    mock_result = MagicMock()
    mock_result.all.return_value = []

    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_leaderboard(mock_db_session, game_id, limit)

    # Verify empty list is returned
    assert result == []


@pytest.mark.unit
def test_get_leaderboard_by_year_returns_year_specific_top(mock_db_session, sample_players):
    """Test get_leaderboard_by_year returns top users for specific year."""
    # Setup
    game_id = 1
    year = 2024
    limit = 2

    # Mock exec result with user balances for specific year
    mock_result = MagicMock()
    mock_result.all.return_value = [
        (sample_players[0], 8),   # Player 1 with 8 coins in 2024
        (sample_players[1], 5)    # Player 2 with 5 coins in 2024
    ]

    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_leaderboard_by_year(mock_db_session, game_id, year, limit)

    # Verify exec was called
    mock_db_session.exec.assert_called_once()

    # Verify correct year-specific leaderboard is returned
    assert len(result) == 2
    assert result[0] == (sample_players[0], 8)
    assert result[1] == (sample_players[1], 5)


@pytest.mark.unit
def test_get_leaderboard_by_year_empty_for_year_with_no_transactions(mock_db_session):
    """Test get_leaderboard_by_year returns empty for year with no transactions."""
    # Setup
    game_id = 1
    year = 2023  # Year with no transactions
    limit = 10

    # Mock exec returning empty result
    mock_result = MagicMock()
    mock_result.all.return_value = []

    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_leaderboard_by_year(mock_db_session, game_id, year, limit)

    # Verify empty list is returned
    assert result == []


@pytest.mark.unit
def test_get_leaderboard_by_year_different_yields_different_results(mock_db_session):
    """Test get_leaderboard_by_year returns different results for different years."""
    # Setup
    game_id = 1
    year_2023 = 2023
    year_2024 = 2024
    limit = 2

    # Create mock players with consistent IDs
    player1 = MagicMock()
    player1.id = 1
    player1.first_name = "Player1"

    player2 = MagicMock()
    player2.id = 2
    player2.first_name = "Player2"

    player3 = MagicMock()
    player3.id = 3
    player3.first_name = "Player3"

    # Mock different results for different years
    mock_result_2023 = MagicMock()
    mock_result_2023.all.return_value = [
        (player2, 12),  # Player 2 with 12 coins in 2023
        (player3, 7)    # Player 3 with 7 coins in 2023
    ]

    mock_result_2024 = MagicMock()
    mock_result_2024.all.return_value = [
        (player1, 15),  # Player 1 with 15 coins in 2024
        (player2, 8)    # Player 2 with 8 coins in 2024
    ]

    # Configure mock to return different results based on year
    call_count = 0

    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        # First call for 2023, second call for 2024
        if call_count == 1:
            return mock_result_2023
        else:
            return mock_result_2024

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute for 2023
    result_2023 = get_leaderboard_by_year(mock_db_session, game_id, year_2023, limit)

    # Execute for 2024
    result_2024 = get_leaderboard_by_year(mock_db_session, game_id, year_2024, limit)

    # Verify different results for different years
    assert len(result_2023) == 2
    assert result_2023[0][1] == 12  # Check amount for player2 in 2023
    assert result_2023[1][1] == 7   # Check amount for player3 in 2023

    assert len(result_2024) == 2
    assert result_2024[0][1] == 15  # Check amount for player1 in 2024
    assert result_2024[1][1] == 8  # Check amount for player2 in 2024

    # Verify that results are different between years
    # The leaderboards should have different top players and amounts
    assert result_2023 != result_2024  # Overall results should be different


@pytest.mark.unit
def test_add_coins_negative_amount_raises_error(mock_db_session):
    """Test add_coins raises ValueError for negative amounts."""
    # Setup
    game_id = 1
    user_id = 1
    amount = -2  # Negative amount should raise error
    year = 2024
    reason = "penalty"

    # Execute and verify ValueError is raised
    with pytest.raises(ValueError, match="Amount must be positive"):
        add_coins(mock_db_session, game_id, user_id, amount, year, reason)

    # Verify no transaction was created
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_not_called()


@pytest.mark.unit
def test_get_balance_handles_negative_transactions(mock_db_session):
    """Test get_balance correctly handles negative transactions."""
    # Setup
    game_id = 1
    user_id = 1
    expected_balance = 3  # 10 + (-5) + (-2) = 3

    # Mock exec returning balance after deductions
    mock_result = MagicMock()
    mock_result.first.return_value = (expected_balance,)

    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_balance(mock_db_session, game_id, user_id)

    # Verify correct balance is returned after deductions
    assert result == expected_balance
