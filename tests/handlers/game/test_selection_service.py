"""Tests for selection service functionality."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from bot.handlers.game.selection_service import (
    select_winner_with_effects,
    build_selection_context,
    SelectionResult
)
from bot.app.models import TGUser, GamePlayerEffect, DoubleChancePurchase


@pytest.mark.unit
def test_select_winner_with_effects_normal_selection(mock_db_session, sample_players):
    """Test select_winner_with_effects with normal selection (no effects)."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)
    players = sample_players[:3]

    # Mock no effects
    def mock_get_effects(db_session, game_id, user_id):
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=None,
            immunity_day=None
        )

    # Mock no double chance purchases
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Patch get_or_create_player_effects
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute
        with patch('random.choice', return_value=players[0]):
            result = select_winner_with_effects(mock_db_session, game_id, players, current_date)

        # Verify
        assert result is not None
        assert result.winner == players[0]
        assert result.had_immunity is False
        assert result.had_double_chance is False
        assert result.all_protected is False
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_select_winner_with_effects_with_immunity_reselection(mock_db_session, sample_players):
    """Test select_winner_with_effects when winner has immunity (reselection occurs)."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 167
    current_year = 2024
    current_day = 167
    players = sample_players[:3]

    # Mock effects: player[0] has immunity, others don't
    def mock_get_effects(db_session, game_id, user_id):
        if user_id == players[0].id:
            return GamePlayerEffect(
                game_id=game_id,
                user_id=user_id,
                immunity_year=current_year,
                immunity_day=current_day
            )
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=None,
            immunity_day=None
        )

    # Mock no double chance purchases
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Patch get_or_create_player_effects
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute - first choice is protected player[0], should reselect to player[1]
        with patch('random.choice') as mock_choice:
            # First call returns protected player, second call returns unprotected
            mock_choice.side_effect = [players[0], players[1]]
            result = select_winner_with_effects(mock_db_session, game_id, players, current_date)

        # Verify
        assert result is not None
        assert result.winner == players[1]
        assert result.had_immunity is True  # Immunity was triggered
        assert result.had_double_chance is False
        assert result.all_protected is False
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_select_winner_with_effects_with_double_chance(mock_db_session, sample_players):
    """Test select_winner_with_effects when winner has double chance."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 166
    current_year = 2024
    current_day = 166
    players = sample_players[:3]

    # Mock no immunity
    def mock_get_effects(db_session, game_id, user_id):
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=None,
            immunity_day=None
        )

    # Mock double chance purchase for player[0]
    purchase = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=players[1].id,
        target_id=players[0].id,
        year=current_year,
        day=current_day,
        is_used=False
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [purchase]
    mock_db_session.exec.return_value = mock_result

    # Patch get_or_create_player_effects
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute - winner has double chance
        with patch('random.choice', return_value=players[0]):
            result = select_winner_with_effects(mock_db_session, game_id, players, current_date)

        # Verify
        assert result is not None
        assert result.winner == players[0]
        assert result.had_immunity is False
        assert result.had_double_chance is True  # Double chance detected
        assert result.all_protected is False
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_select_winner_with_effects_all_protected(mock_db_session, sample_players):
    """Test select_winner_with_effects when all players are protected."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 167
    current_year = 2024
    current_day = 167
    players = sample_players[:3]

    # Mock all players protected
    def mock_get_effects(db_session, game_id, user_id):
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=current_year,
            immunity_day=current_day
        )

    # Mock no double chance purchases
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Patch get_or_create_player_effects
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute
        result = select_winner_with_effects(mock_db_session, game_id, players, current_date)

        # Verify
        assert result is not None
        assert result.winner is None  # No winner when all protected
        assert result.had_immunity is False
        assert result.had_double_chance is False
        assert result.all_protected is True  # All protected flag set
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_select_winner_with_effects_immunity_and_double_chance(mock_db_session, sample_players):
    """Test select_winner_with_effects with both immunity triggering reselection and double chance on new winner."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 166
    current_year = 2024
    current_day = 166
    players = sample_players[:3]

    # Mock effects: player[0] has immunity, others don't
    def mock_get_effects(db_session, game_id, user_id):
        if user_id == players[0].id:
            return GamePlayerEffect(
                game_id=game_id,
                user_id=user_id,
                immunity_year=current_year,
                immunity_day=current_day
            )
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=None,
            immunity_day=None
        )

    # Mock double chance purchase for player[1]
    purchase = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=players[2].id,
        target_id=players[1].id,
        year=current_year,
        day=current_day,
        is_used=False
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [purchase]
    mock_db_session.exec.return_value = mock_result

    # Patch functions
    import bot.handlers.game.game_effects_service as ges
    import bot.handlers.game.selection_service

    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute with mocked random.choice
        with patch('bot.handlers.game.selection_service.random.choice') as mock_choice, \
             patch('bot.handlers.game.selection_service.check_winner_immunity') as mock_check:

            # First call: select from pool (returns protected player[0])
            # Second call: select from unprotected_players (returns player[1])
            mock_choice.side_effect = [players[0], players[1]]

            # Mock check_winner_immunity to return True for player[0]
            mock_check.return_value = True

            result = select_winner_with_effects(mock_db_session, game_id, players, current_date)

        # Verify
        assert result is not None
        assert result.winner == players[1]  # Reselected to player[1]
        assert result.had_immunity is True  # Immunity was triggered
        assert result.had_double_chance is True  # player[1] has double chance
        assert result.all_protected is False

        # Verify check_winner_immunity was called with player[0]
        mock_check.assert_called_once()
        assert mock_check.call_args[0][2] == players[0]  # Third arg is winner
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_select_winner_with_effects_immunity_disabled(mock_db_session, sample_players):
    """Test select_winner_with_effects when immunity is disabled."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 167
    current_year = 2024
    current_day = 167
    players = sample_players[:3]

    # Mock player[0] has immunity (but it should be ignored)
    def mock_get_effects(db_session, game_id, user_id):
        if user_id == players[0].id:
            return GamePlayerEffect(
                game_id=game_id,
                user_id=user_id,
                immunity_year=current_year,
                immunity_day=current_day
            )
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=None,
            immunity_day=None
        )

    # Mock no double chance purchases
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Patch get_or_create_player_effects
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute with immunity_enabled=False
        with patch('random.choice', return_value=players[0]):
            result = select_winner_with_effects(
                mock_db_session, game_id, players, current_date, immunity_enabled=False
            )

        # Verify - protected player can win when immunity is disabled
        assert result is not None
        assert result.winner == players[0]
        assert result.had_immunity is False  # Immunity not checked
        assert result.had_double_chance is False
        assert result.all_protected is False
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_build_selection_context_normal(mock_db_session, sample_players):
    """Test build_selection_context with normal scenario."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)
    players = sample_players[:3]

    # Mock no effects
    def mock_get_effects(db_session, game_id, user_id):
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=None,
            immunity_day=None
        )

    # Mock no double chance purchases
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Patch get_or_create_player_effects
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute
        selection_pool, unprotected, protected, double_chance_ids = build_selection_context(
            mock_db_session, game_id, players, current_date
        )

        # Verify
        assert len(selection_pool) == 3
        assert len(unprotected) == 3
        assert len(protected) == 0
        assert len(double_chance_ids) == 0
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_build_selection_context_with_protection(mock_db_session, sample_players):
    """Test build_selection_context with some players protected."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 167
    current_year = 2024
    current_day = 167
    players = sample_players[:3]

    # Mock player[0] protected
    def mock_get_effects(db_session, game_id, user_id):
        if user_id == players[0].id:
            return GamePlayerEffect(
                game_id=game_id,
                user_id=user_id,
                immunity_year=current_year,
                immunity_day=current_day
            )
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=None,
            immunity_day=None
        )

    # Mock no double chance purchases
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Patch get_or_create_player_effects
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute
        selection_pool, unprotected, protected, double_chance_ids = build_selection_context(
            mock_db_session, game_id, players, current_date
        )

        # Verify
        assert len(selection_pool) == 3  # All in pool (protection checked later)
        assert len(unprotected) == 2
        assert len(protected) == 1
        assert players[0] in protected
        assert len(double_chance_ids) == 0
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_build_selection_context_with_double_chance(mock_db_session, sample_players):
    """Test build_selection_context with double chance players."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 166
    current_year = 2024
    current_day = 166
    players = sample_players[:3]

    # Mock no immunity
    def mock_get_effects(db_session, game_id, user_id):
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=None,
            immunity_day=None
        )

    # Mock double chance purchase for player[0]
    purchase = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=players[1].id,
        target_id=players[0].id,
        year=current_year,
        day=current_day,
        is_used=False
    )

    mock_result = MagicMock()
    mock_result.all.return_value = [purchase]
    mock_db_session.exec.return_value = mock_result

    # Patch get_or_create_player_effects
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute
        selection_pool, unprotected, protected, double_chance_ids = build_selection_context(
            mock_db_session, game_id, players, current_date
        )

        # Verify
        assert len(selection_pool) == 4  # player[0] twice + player[1] + player[2]
        assert selection_pool.count(players[0]) == 2
        assert len(unprotected) == 3
        assert len(protected) == 0
        assert players[0].id in double_chance_ids
        assert len(double_chance_ids) == 1
    finally:
        ges.get_or_create_player_effects = original_get_effects


@pytest.mark.unit
def test_build_selection_context_immunity_disabled(mock_db_session, sample_players):
    """Test build_selection_context when immunity is disabled."""
    # Setup
    game_id = 1
    current_date = date(2024, 6, 15)  # Day 167
    current_year = 2024
    current_day = 167
    players = sample_players[:3]

    # Mock player[0] has immunity (but should be ignored)
    def mock_get_effects(db_session, game_id, user_id):
        if user_id == players[0].id:
            return GamePlayerEffect(
                game_id=game_id,
                user_id=user_id,
                immunity_year=current_year,
                immunity_day=current_day
            )
        return GamePlayerEffect(
            game_id=game_id,
            user_id=user_id,
            immunity_year=None,
            immunity_day=None
        )

    # Mock no double chance purchases
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Patch get_or_create_player_effects
    import bot.handlers.game.game_effects_service as ges
    original_get_effects = ges.get_or_create_player_effects
    ges.get_or_create_player_effects = mock_get_effects

    try:
        # Execute with immunity_enabled=False
        selection_pool, unprotected, protected, double_chance_ids = build_selection_context(
            mock_db_session, game_id, players, current_date, immunity_enabled=False
        )

        # Verify - all players unprotected when immunity disabled
        assert len(selection_pool) == 3
        assert len(unprotected) == 3  # All unprotected
        assert len(protected) == 0  # None protected
        assert len(double_chance_ids) == 0
    finally:
        ges.get_or_create_player_effects = original_get_effects
