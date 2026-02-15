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
    from bot.handlers.game.shop_service import get_or_create_player_effects

    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 167
    current_year = 2024
    current_day = 167

    # Create test players
    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    player3 = TGUser(id=3, tg_id=103, first_name="Player3", username="player3")
    players = [player1, player2, player3]

    # Mock effects: player1 protected today, player2 and player3 not protected
    effect1 = GamePlayerEffect(
        game_id=game_id,
        user_id=player1.id,
        immunity_year=current_year,
        immunity_day=current_day  # Protected today
    )

    effect2 = GamePlayerEffect(
        game_id=game_id,
        user_id=player2.id,
        immunity_year=None,
        immunity_day=None  # Not protected
    )

    effect3 = GamePlayerEffect(
        game_id=game_id,
        user_id=player3.id,
        immunity_year=2024,
        immunity_day=166  # Protection expired yesterday
    )

    # Mock get_or_create_player_effects
    def mock_get_effects(db_session, game_id, user_id):
        if user_id == player1.id:
            return effect1
        elif user_id == player2.id:
            return effect2
        else:
            return effect3

    # Patch the function in game_effects_service where it's used
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute
        unprotected, protected = filter_protected_players(mock_db_session, game_id, players, current_date)

        # Verify
        assert len(unprotected) == 2
        assert len(protected) == 1
        assert player1 in protected
        assert player2 in unprotected
        assert player3 in unprotected
    finally:
        # Restore original function
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_filter_protected_players_all_protected(mock_db_session):
    """Test filter_protected_players when all players are protected."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 167
    current_year = 2024
    current_day = 167

    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    players = [player1, player2]

    # Mock all players protected today
    def mock_get_effects(db_session, game_id, user_id):
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=current_year,
            immunity_day=current_day
        )

    # Patch the function
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute
        unprotected, protected = filter_protected_players(mock_db_session, game_id, players, current_date)

        # Verify
        assert len(unprotected) == 0
        assert len(protected) == 2
    finally:
        ges.get_or_create_player_effects = original_get_effects


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
    effect = GamePlayerEffect(
        game_id=game_id,
        user_id=0,
        immunity_year=None,
        immunity_day=None
    )

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
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 166
    current_year = 2024
    current_day = 166

    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    players = [player1, player2]

    # Mock double chance purchases: player1 has active purchase for today
    purchase1 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=3,
        target_id=player1.id,
        year=current_year,
        day=current_day,
        is_used=False
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [purchase1]
    mock_db_session.exec.return_value = mock_result

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
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 166
    current_year = 2024
    current_day = 166

    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    player3 = TGUser(id=3, tg_id=103, first_name="Player3", username="player3")
    players = [player1, player2, player3]

    # Mock double chance purchases: player1 and player3 have active purchases (1 each)
    purchase1 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=4,
        target_id=player1.id,
        year=current_year,
        day=current_day,
        is_used=False
    )
    purchase3 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=5,
        target_id=player3.id,
        year=current_year,
        day=current_day,
        is_used=False
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [purchase1, purchase3]
    mock_db_session.exec.return_value = mock_result

    # Execute
    pool, double_chance_players = build_selection_pool(mock_db_session, game_id, players, current_date)

    # Verify - with exponential logic: 1 purchase = 2^1 = 2 entries
    assert len(pool) == 5  # player1 (2^1=2) + player2 (1) + player3 (2^1=2)
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
    current_date = date(2024, 6, 15)  # Day 167
    current_year = 2024
    current_day = 167
    winner = TGUser(id=1, tg_id=101, first_name="Winner", username="winner")

    # Mock effect with active immunity for today
    effect = GamePlayerEffect(
        game_id=game_id,
        user_id=winner.id,
        immunity_year=current_year,
        immunity_day=current_day
    )

    # Mock get_or_create_player_effects
    def mock_get_effects(db_session, game_id, user_id):
        return effect

    # Patch the function
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute
        result = check_winner_immunity(mock_db_session, game_id, winner, current_date)

        # Verify
        assert result is True
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_check_winner_immunity_expired(mock_db_session):
    """Test check_winner_immunity returns False when immunity is expired."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 166
    winner = TGUser(id=1, tg_id=101, first_name="Winner", username="winner")

    # Mock effect with expired immunity (yesterday)
    effect = GamePlayerEffect(
        game_id=game_id,
        user_id=winner.id,
        immunity_year=2024,
        immunity_day=165  # Yesterday
    )

    mock_result = MagicMock()
    mock_result.first.return_value = effect
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = check_winner_immunity(mock_db_session, game_id, winner, current_date)

    # Verify
    assert result is False


@pytest.mark.unit
def test_reset_double_chance(mock_db_session):
    """Test reset_double_chance marks purchases as used."""
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    user_id = 1
    current_date = date(2024, 6, 15)  # Day 166
    current_year = 2024
    current_day = 166

    # Mock active double chance purchases for today
    purchase1 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=2,
        target_id=user_id,
        year=current_year,
        day=current_day,
        is_used=False
    )
    purchase2 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=3,
        target_id=user_id,
        year=current_year,
        day=current_day,
        is_used=False
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [purchase1, purchase2]
    mock_db_session.exec.return_value = mock_result

    # Execute
    reset_double_chance(mock_db_session, game_id, user_id, current_date)

    # Verify both purchases are marked as used
    assert purchase1.is_used is True
    assert purchase2.is_used is True
    assert mock_db_session.add.call_count == 2


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


@pytest.mark.unit
def test_build_selection_pool_exponential_double_chance(mock_db_session):
    """Test build_selection_pool with exponential logic - 2 purchases = 4 entries."""
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 166
    current_year = 2024
    current_day = 166

    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    players = [player1, player2]

    # Mock double chance purchases: player1 has 2 purchases from different buyers
    purchase1 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=3,
        target_id=player1.id,
        year=current_year,
        day=current_day,
        is_used=False
    )
    purchase2 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=4,
        target_id=player1.id,
        year=current_year,
        day=current_day,
        is_used=False
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [purchase1, purchase2]
    mock_db_session.exec.return_value = mock_result

    # Execute
    pool, double_chance_players = build_selection_pool(mock_db_session, game_id, players, current_date)

    # Verify - with exponential logic: 2 purchases = 2^2 = 4 entries
    assert len(pool) == 5  # player1 (2^2=4) + player2 (1)
    assert pool.count(player1) == 4
    assert pool.count(player2) == 1
    assert len(double_chance_players) == 1
    assert player1.id in double_chance_players


@pytest.mark.unit
def test_build_selection_pool_triple_double_chance(mock_db_session):
    """Test build_selection_pool with exponential logic - 3 purchases = 8 entries."""
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 166
    current_year = 2024
    current_day = 166

    player1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    player2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")
    player3 = TGUser(id=3, tg_id=103, first_name="Player3", username="player3")
    players = [player1, player2, player3]

    # Mock double chance purchases: player1 has 3 purchases from different buyers
    purchase1 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=4,
        target_id=player1.id,
        year=current_year,
        day=current_day,
        is_used=False
    )
    purchase2 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=5,
        target_id=player1.id,
        year=current_year,
        day=current_day,
        is_used=False
    )
    purchase3 = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=6,
        target_id=player1.id,
        year=current_year,
        day=current_day,
        is_used=False
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [purchase1, purchase2, purchase3]
    mock_db_session.exec.return_value = mock_result

    # Execute
    pool, double_chance_players = build_selection_pool(mock_db_session, game_id, players, current_date)

    # Verify - with exponential logic: 3 purchases = 2^3 = 8 entries
    assert len(pool) == 10  # player1 (2^3=8) + player2 (1) + player3 (1)
    assert pool.count(player1) == 8
    assert pool.count(player2) == 1
    assert pool.count(player3) == 1
    assert len(double_chance_players) == 1
    assert player1.id in double_chance_players
