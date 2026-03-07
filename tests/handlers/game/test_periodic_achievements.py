"""Tests for periodic achievements functionality."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date

from bot.handlers.game.achievement_service import (
    get_monthly_winners,
    get_monthly_initiators,
    check_monthly_achievements,
    is_first_game_of_month,
    get_previous_month,
)
from bot.app.models import UserAchievement, GameResult, PidorCoinTransaction


@pytest.mark.unit
def test_get_previous_month_january():
    """Test get_previous_month for January returns December of previous year."""
    year, month = get_previous_month(2024, 1)
    assert year == 2023
    assert month == 12


@pytest.mark.unit
def test_get_previous_month_regular():
    """Test get_previous_month for regular months."""
    year, month = get_previous_month(2024, 6)
    assert year == 2024
    assert month == 5


@pytest.mark.unit
def test_is_first_game_of_month_true(mock_db_session):
    """Test is_first_game_of_month returns True when no previous games."""
    # Setup
    game_id = 1
    year = 2024
    month = 6
    day = 15

    # Mock exec to return empty list (no previous games)
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = is_first_game_of_month(mock_db_session, game_id, year, month, day)

    # Verify
    assert result is True


@pytest.mark.unit
def test_is_first_game_of_month_false(mock_db_session):
    """Test is_first_game_of_month returns False when previous games exist."""
    # Setup
    game_id = 1
    year = 2024
    month = 6
    day = 15

    # Mock previous game on day 5 of the month
    previous_game = GameResult(
        id=1,
        game_id=game_id,
        winner_id=1,
        year=2024,
        day=date(2024, 6, 5).timetuple().tm_yday
    )

    # Mock exec to return previous game
    mock_result = MagicMock()
    mock_result.all.return_value = [previous_game]
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = is_first_game_of_month(mock_db_session, game_id, year, month, day)

    # Verify
    assert result is False


@pytest.mark.unit
def test_get_monthly_winners_single_winner(mock_db_session):
    """Test get_monthly_winners returns single winner."""
    # Setup
    game_id = 1
    year = 2024
    month = 6

    # Mock exec to return single winner with 5 wins
    mock_result = MagicMock()
    mock_result.all.return_value = [(1, 5)]  # user_id=1, wins=5
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_monthly_winners(mock_db_session, game_id, year, month)

    # Verify
    assert len(result) == 1
    assert result[0] == (1, 5)


@pytest.mark.unit
def test_get_monthly_winners_multiple_winners(mock_db_session):
    """Test get_monthly_winners returns multiple winners sorted by wins."""
    # Setup
    game_id = 1
    year = 2024
    month = 6

    # Mock exec to return multiple winners
    mock_result = MagicMock()
    mock_result.all.return_value = [
        (1, 10),  # user_id=1, wins=10
        (2, 7),   # user_id=2, wins=7
        (3, 5),   # user_id=3, wins=5
    ]
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_monthly_winners(mock_db_session, game_id, year, month)

    # Verify
    assert len(result) == 3
    assert result[0] == (1, 10)
    assert result[1] == (2, 7)
    assert result[2] == (3, 5)


@pytest.mark.unit
def test_get_monthly_winners_no_games(mock_db_session):
    """Test get_monthly_winners returns empty list when no games."""
    # Setup
    game_id = 1
    year = 2024
    month = 6

    # Mock exec to return empty list
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_monthly_winners(mock_db_session, game_id, year, month)

    # Verify
    assert len(result) == 0


@pytest.mark.unit
def test_get_monthly_initiators_single_initiator(mock_db_session):
    """Test get_monthly_initiators returns single initiator."""
    # Setup
    game_id = 1
    year = 2024
    month = 6

    # Mock exec to return single initiator with 15 commands
    mock_result = MagicMock()
    mock_result.all.return_value = [(1, 15)]  # user_id=1, commands=15
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_monthly_initiators(mock_db_session, game_id, year, month)

    # Verify
    assert len(result) == 1
    assert result[0] == (1, 15)


@pytest.mark.unit
def test_get_monthly_initiators_multiple_initiators(mock_db_session):
    """Test get_monthly_initiators returns multiple initiators sorted by commands."""
    # Setup
    game_id = 1
    year = 2024
    month = 6

    # Mock exec to return multiple initiators
    mock_result = MagicMock()
    mock_result.all.return_value = [
        (1, 20),  # user_id=1, commands=20
        (2, 15),  # user_id=2, commands=15
        (3, 10),  # user_id=3, commands=10
    ]
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_monthly_initiators(mock_db_session, game_id, year, month)

    # Verify
    assert len(result) == 3
    assert result[0] == (1, 20)
    assert result[1] == (2, 15)
    assert result[2] == (3, 10)


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.get_monthly_winners')
@patch('bot.handlers.game.achievement_service.get_monthly_initiators')
@patch('bot.handlers.game.achievement_service.award_achievement')
def test_check_monthly_achievements_single_winner(
    mock_award_achievement,
    mock_get_initiators,
    mock_get_winners,
    mock_db_session
):
    """Test check_monthly_achievements awards to single winner and initiator."""
    # Setup
    game_id = 1
    year = 2024
    month = 6

    # Mock single winner and initiator
    mock_get_winners.return_value = [(1, 10)]  # user_id=1, 10 wins
    mock_get_initiators.return_value = [(2, 15)]  # user_id=2, 15 commands

    # Mock award_achievement to return achievements
    def award_side_effect(db, gid, uid, code, y, period=None):
        return UserAchievement(
            id=1,
            game_id=gid,
            user_id=uid,
            achievement_code=code,
            year=y,
            period=period,
            earned_at=datetime.utcnow()
        )

    mock_award_achievement.side_effect = award_side_effect

    # Execute
    result = check_monthly_achievements(mock_db_session, game_id, year, month)

    # Verify
    assert len(result) == 2
    assert mock_award_achievement.call_count == 2

    # Verify monthly_king was awarded to user 1
    king_call = mock_award_achievement.call_args_list[0]
    assert king_call[0][2] == 1  # user_id
    assert king_call[0][3] == "monthly_king"
    assert king_call[1]['period'] == month

    # Verify monthly_initiator was awarded to user 2
    initiator_call = mock_award_achievement.call_args_list[1]
    assert initiator_call[0][2] == 2  # user_id
    assert initiator_call[0][3] == "monthly_initiator"
    assert initiator_call[1]['period'] == month


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.get_monthly_winners')
@patch('bot.handlers.game.achievement_service.get_monthly_initiators')
@patch('bot.handlers.game.achievement_service.award_achievement')
def test_check_monthly_achievements_tie(
    mock_award_achievement,
    mock_get_initiators,
    mock_get_winners,
    mock_db_session
):
    """Test check_monthly_achievements awards to all tied winners."""
    # Setup
    game_id = 1
    year = 2024
    month = 6

    # Mock tied winners (both have 10 wins)
    mock_get_winners.return_value = [
        (1, 10),  # user_id=1, 10 wins
        (2, 10),  # user_id=2, 10 wins (tie)
        (3, 8),   # user_id=3, 8 wins (less)
    ]

    # Mock tied initiators (both have 15 commands)
    mock_get_initiators.return_value = [
        (4, 15),  # user_id=4, 15 commands
        (5, 15),  # user_id=5, 15 commands (tie)
        (6, 10),  # user_id=6, 10 commands (less)
    ]

    # Mock award_achievement to return achievements
    achievements = []
    def award_side_effect(db, gid, uid, code, y, period=None):
        achievement = UserAchievement(
            id=len(achievements) + 1,
            game_id=gid,
            user_id=uid,
            achievement_code=code,
            year=y,
            period=period,
            earned_at=datetime.utcnow()
        )
        achievements.append(achievement)
        return achievement

    mock_award_achievement.side_effect = award_side_effect

    # Execute
    result = check_monthly_achievements(mock_db_session, game_id, year, month)

    # Verify - should award to 2 kings and 2 initiators (4 total)
    assert len(result) == 4
    assert mock_award_achievement.call_count == 4

    # Verify both tied winners got monthly_king
    king_calls = [call for call in mock_award_achievement.call_args_list
                  if call[0][3] == "monthly_king"]
    assert len(king_calls) == 2
    king_user_ids = {call[0][2] for call in king_calls}
    assert king_user_ids == {1, 2}

    # Verify both tied initiators got monthly_initiator
    initiator_calls = [call for call in mock_award_achievement.call_args_list
                       if call[0][3] == "monthly_initiator"]
    assert len(initiator_calls) == 2
    initiator_user_ids = {call[0][2] for call in initiator_calls}
    assert initiator_user_ids == {4, 5}


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.get_monthly_winners')
@patch('bot.handlers.game.achievement_service.get_monthly_initiators')
@patch('bot.handlers.game.achievement_service.award_achievement')
def test_check_monthly_achievements_no_games(
    mock_award_achievement,
    mock_get_initiators,
    mock_get_winners,
    mock_db_session
):
    """Test check_monthly_achievements returns empty list when no games."""
    # Setup
    game_id = 1
    year = 2024
    month = 6

    # Mock no winners or initiators
    mock_get_winners.return_value = []
    mock_get_initiators.return_value = []

    # Execute
    result = check_monthly_achievements(mock_db_session, game_id, year, month)

    # Verify
    assert len(result) == 0
    mock_award_achievement.assert_not_called()


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.get_monthly_winners')
@patch('bot.handlers.game.achievement_service.get_monthly_initiators')
@patch('bot.handlers.game.achievement_service.award_achievement')
def test_monthly_achievements_not_awarded_twice(
    mock_award_achievement,
    mock_get_initiators,
    mock_get_winners,
    mock_db_session
):
    """Test monthly achievements are not awarded twice for same period."""
    # Setup
    game_id = 1
    year = 2024
    month = 6

    # Mock single winner
    mock_get_winners.return_value = [(1, 10)]
    mock_get_initiators.return_value = [(2, 15)]

    # Mock award_achievement to return None (already has achievement)
    mock_award_achievement.return_value = None

    # Execute
    result = check_monthly_achievements(mock_db_session, game_id, year, month)

    # Verify - no achievements awarded (already had them)
    assert len(result) == 0
    assert mock_award_achievement.call_count == 2  # Tried to award but returned None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_monthly_achievements_awarded_on_first_game(
    mock_update,
    mock_context,
    mock_game,
    sample_players,
    mocker
):
    """Integration test: monthly achievements awarded on first game of new month."""
    from bot.handlers.game.commands import pidor_cmd
    from bot.handlers.game.config import GameConstants
    from unittest.mock import AsyncMock

    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game
    winner = sample_players[0]

    # Mock query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None

    mock_context.db_session.query.side_effect = [
        mock_game_query, mock_missed_query, mock_result_query
    ]

    # Mock datetime - first day of July (month 7)
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 7
    mock_dt.day = 1
    mock_dt.timetuple.return_value.tm_yday = 183  # July 1st
    mock_dt.date.return_value = MagicMock()
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        winner,
        "Stage 1", "Stage 2", "Stage 3", "Stage 4: {username}",
    ])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep', new_callable=AsyncMock)

    # Mock get_or_create_player_effects
    mocker.patch('bot.handlers.game.game_effects_service.get_or_create_player_effects',
                 return_value=MagicMock(immunity_year=None, immunity_day=None))

    # Mock is_first_game_of_month to return True
    mocker.patch('bot.handlers.game.achievement_service.is_first_game_of_month',
                 return_value=True)

    # Mock get_monthly_winners and get_monthly_initiators for June
    mocker.patch('bot.handlers.game.achievement_service.get_monthly_winners',
                 return_value=[(winner.id, 15)])  # Winner had 15 wins in June
    mocker.patch('bot.handlers.game.achievement_service.get_monthly_initiators',
                 return_value=[(winner.id, 20)])  # Winner had 20 commands in June

    # Mock exec
    def mock_exec_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()

        if 'prediction' in stmt_str:
            mock_result.all.return_value = []
        elif 'userachievement' in stmt_str:
            # No achievements yet
            mock_result.first.return_value = None
            mock_result.all.return_value = []
        elif 'gameresult' in stmt_str:
            # First win of the year
            mock_result.all.return_value = [MagicMock()]
        else:
            mock_result.all.return_value = []
            mock_result.first.return_value = None

        return mock_result

    mock_context.db_session.exec.side_effect = mock_exec_side_effect

    # Mock add_coins
    mocker.patch('bot.handlers.game.commands.add_coins')
    mocker.patch('bot.handlers.game.achievement_service.add_coins')
    mocker.patch('bot.handlers.game.commands.get_balance', return_value=10)

    # Mock get_config_by_game_id
    mock_config = MagicMock()
    mock_config.constants = GameConstants()
    mock_config.constants.achievements_enabled = True
    mocker.patch('bot.handlers.game.achievement_service.get_config_by_game_id',
                 return_value=mock_config)
    mocker.patch('bot.handlers.game.prediction_service.get_config_by_game_id',
                 return_value=mock_config)

    # Mock send_result_with_reroll_button
    mocker.patch('bot.handlers.game.commands.send_result_with_reroll_button',
                 new_callable=AsyncMock)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify monthly achievements were added
    add_calls = [call for call in mock_context.db_session.add.call_args_list]
    monthly_achievements = []
    for call in add_calls:
        if len(call[0]) > 0 and isinstance(call[0][0], UserAchievement):
            achievement = call[0][0]
            if achievement.achievement_code in ["monthly_king", "monthly_initiator"]:
                monthly_achievements.append(achievement)

    # Should have both monthly_king and monthly_initiator
    assert len(monthly_achievements) >= 2, "Should award monthly achievements on first game of month"

    # Verify monthly_king was awarded
    king_achievements = [a for a in monthly_achievements if a.achievement_code == "monthly_king"]
    assert len(king_achievements) > 0, "Should award monthly_king"
    assert king_achievements[0].period == 6, "Should be for June (month 6)"

    # Verify monthly_initiator was awarded
    initiator_achievements = [a for a in monthly_achievements if a.achievement_code == "monthly_initiator"]
    assert len(initiator_achievements) > 0, "Should award monthly_initiator"
    assert initiator_achievements[0].period == 6, "Should be for June (month 6)"
