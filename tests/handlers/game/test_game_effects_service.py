"""Tests for game effects service functionality."""
import pytest
from unittest.mock import MagicMock
from datetime import date, datetime

from bot.handlers.game.game_effects_service import (
    filter_protected_players,
    build_selection_pool,
    check_winner_immunity,
    reset_double_chance,
    is_immunity_enabled
)
from bot.app.models import TGUser, GamePlayerEffect


@pytest.mark.unit
def test_filter_protected_players_separates_correctly(mock_db_session):
    """Test filter_protected_players correctly separates protected and unprotected players."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)

    # Create test players
    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    player3 = TGUser(id=3, tg_id=103, first_name="Player3", username="player3")
    players = [player1, player2, player3]

    # Mock effects: player1 protected, player2 and player3 not protected
    effect1 = MagicMock()
    effect1.immunity_until = date(2024, 6, 16)  # Protected until tomorrow

    effect2 = MagicMock()
    effect2.immunity_until = None  # Not protected

    effect3 = MagicMock()
    effect3.immunity_until = date(2024, 6, 14)  # Protection expired

    # Configure exec to return different effects
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        mock_result = MagicMock()
        if call_count == 1:
            mock_result.first.return_value = effect1
        elif call_count == 2:
            mock_result.first.return_value = effect2
        else:
            mock_result.first.return_value = effect3
        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    unprotected, protected = filter_protected_players(mock_db_session, game_id, players, current_date)

    # Verify
    assert len(unprotected) == 2
    assert len(protected) == 1
    assert player1 in protected
    assert player2 in unprotected
    assert player3 in unprotected


@pytest.mark.unit
def test_filter_protected_players_all_protected(mock_db_session):
    """Test filter_protected_players when all players are protected."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)

    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    players = [player1, player2]

    # Mock all players protected
    effect = MagicMock()
    effect.immunity_until = date(2024, 6, 16)

    mock_result = MagicMock()
    mock_result.first.return_value = effect
    mock_db_session.exec.return_value = mock_result

    # Execute
    unprotected, protected = filter_protected_players(mock_db_session, game_id, players, current_date)

    # Verify
    assert len(unprotected) == 0
    assert len(protected) == 2


@pytest.mark.unit
def test_filter_protected_players_none_protected(mock_db_session):
    """Test filter_protected_players when no players are protected."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)

    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    players = [player1, player2]

    # Mock no players protected
    effect = MagicMock()
    effect.immunity_until = None

    mock_result = MagicMock()
    mock_result.first.return_value = effect
    mock_db_session.exec.return_value = mock_result

    # Execute
    unprotected, protected = filter_protected_players(mock_db_session, game_id, players, current_date)

    # Verify
    assert len(unprotected) == 2
    assert len(protected) == 0


@pytest.mark.unit
def test_build_selection_pool_with_double_chance(mock_db_session):
    """Test build_selection_pool adds players with double chance twice."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)

    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    players = [player1, player2]

    # Mock effects: player1 has double chance, player2 doesn't
    effect1 = MagicMock()
    effect1.double_chance_until = date(2024, 6, 16)  # Active until tomorrow

    effect2 = MagicMock()
    effect2.double_chance_until = None

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        mock_result = MagicMock()
        if call_count == 1:
            mock_result.first.return_value = effect1
        else:
            mock_result.first.return_value = effect2
        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    pool, double_chance_players = build_selection_pool(mock_db_session, game_id, players, current_date)

    # Verify
    assert len(pool) == 3  # player1 twice + player2 once
    assert pool.count(player1) == 2
    assert pool.count(player2) == 1
    assert player1.id in double_chance_players
    assert player2.id not in double_chance_players


@pytest.mark.unit
def test_build_selection_pool_multiple_double_chance(mock_db_session):
    """Test build_selection_pool with multiple players having double chance."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)

    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    player3 = TGUser(id=3, tg_id=103, first_name="Player3", username="player3")
    players = [player1, player2, player3]

    # Mock effects: player1 and player3 have double chance
    effect1 = MagicMock()
    effect1.double_chance_until = date(2024, 6, 16)

    effect2 = MagicMock()
    effect2.double_chance_until = None

    effect3 = MagicMock()
    effect3.double_chance_until = date(2024, 6, 16)

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        mock_result = MagicMock()
        if call_count == 1:
            mock_result.first.return_value = effect1
        elif call_count == 2:
            mock_result.first.return_value = effect2
        else:
            mock_result.first.return_value = effect3
        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    pool, double_chance_players = build_selection_pool(mock_db_session, game_id, players, current_date)

    # Verify
    assert len(pool) == 5  # player1 twice + player2 once + player3 twice
    assert pool.count(player1) == 2
    assert pool.count(player2) == 1
    assert pool.count(player3) == 2
    assert len(double_chance_players) == 2
    assert player1.id in double_chance_players
    assert player3.id in double_chance_players


@pytest.mark.unit
def test_check_winner_immunity_active(mock_db_session):
    """Test check_winner_immunity returns True when winner is protected."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)
    winner = TGUser(id=1, tg_id=101, first_name="Winner", username="winner")

    # Mock effect with active immunity
    effect = MagicMock()
    effect.immunity_until = date(2024, 6, 16)

    mock_result = MagicMock()
    mock_result.first.return_value = effect
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = check_winner_immunity(mock_db_session, game_id, winner, current_date)

    # Verify
    assert result is True


@pytest.mark.unit
def test_check_winner_immunity_expired(mock_db_session):
    """Test check_winner_immunity returns False when immunity is expired."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)
    winner = TGUser(id=1, tg_id=101, first_name="Winner", username="winner")

    # Mock effect with expired immunity
    effect = MagicMock()
    effect.immunity_until = date(2024, 6, 14)  # Expired yesterday

    mock_result = MagicMock()
    mock_result.first.return_value = effect
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = check_winner_immunity(mock_db_session, game_id, winner, current_date)

    # Verify
    assert result is False


@pytest.mark.unit
def test_reset_double_chance(mock_db_session):
    """Test reset_double_chance clears double chance for user."""
    # Setup
    game_id = 1
    user_id = 1
    current_date = date(2024, 6, 15)

    # Mock effect with active double chance
    effect = MagicMock()
    effect.double_chance_until = date(2024, 6, 16)

    mock_result = MagicMock()
    mock_result.first.return_value = effect
    mock_db_session.exec.return_value = mock_result

    # Execute
    reset_double_chance(mock_db_session, game_id, user_id, current_date)

    # Verify
    assert effect.double_chance_until is None


@pytest.mark.unit
def test_is_immunity_enabled_normal_day():
    """Test is_immunity_enabled returns True on normal day."""
    # Setup - normal day (not December 31)
    current_dt = datetime(2024, 6, 15, 12, 0, 0)

    # Execute
    result = is_immunity_enabled(current_dt)

    # Verify
    assert result is True


@pytest.mark.unit
def test_is_immunity_enabled_last_day():
    """Test is_immunity_enabled returns False on last day of year."""
    # Setup - December 31
    current_dt = datetime(2024, 12, 31, 12, 0, 0)

    # Execute
    result = is_immunity_enabled(current_dt)

    # Verify
    assert result is False
