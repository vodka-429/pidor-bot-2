"""Tests for achievement service functionality."""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, date

from bot.handlers.game.achievement_service import (
    has_achievement,
    award_achievement,
    get_user_achievements,
    get_current_win_streak,
    check_first_blood,
    check_streak_achievements,
    check_and_award_achievements,
)
from bot.app.models import UserAchievement, GameResult
from bot.handlers.game.config import GameConstants, ChatConfig


@pytest.mark.unit
def test_has_achievement_false(mock_db_session):
    """Test has_achievement returns False when achievement doesn't exist."""
    # Setup
    game_id = 1
    user_id = 1
    achievement_code = "first_blood"
    year = 2024

    # Mock exec to return None (no achievement)
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = has_achievement(mock_db_session, game_id, user_id, achievement_code, year)

    # Verify
    assert result is False


@pytest.mark.unit
def test_has_achievement_true(mock_db_session):
    """Test has_achievement returns True when achievement exists."""
    # Setup
    game_id = 1
    user_id = 1
    achievement_code = "first_blood"
    year = 2024

    # Mock existing achievement
    existing_achievement = UserAchievement(
        id=1,
        game_id=game_id,
        user_id=user_id,
        achievement_code=achievement_code,
        year=year,
        period=None,
        earned_at=datetime.utcnow()
    )

    # Mock exec to return achievement
    mock_result = MagicMock()
    mock_result.first.return_value = existing_achievement
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = has_achievement(mock_db_session, game_id, user_id, achievement_code, year)

    # Verify
    assert result is True


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.add_coins')
def test_award_achievement_success(mock_add_coins, mock_db_session):
    """Test award_achievement successfully awards achievement and coins."""
    # Setup
    game_id = 1
    user_id = 1
    achievement_code = "first_blood"
    year = 2024

    # Mock no existing achievement
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = award_achievement(mock_db_session, game_id, user_id, achievement_code, year)

    # Verify achievement was created
    assert result is not None
    assert isinstance(result, UserAchievement)
    assert result.game_id == game_id
    assert result.user_id == user_id
    assert result.achievement_code == achievement_code
    assert result.year == year
    assert result.period is None

    # Verify achievement was added to session
    mock_db_session.add.assert_called_once()
    added_achievement = mock_db_session.add.call_args[0][0]
    assert isinstance(added_achievement, UserAchievement)

    # Verify coins were awarded (10 coins for first_blood)
    mock_add_coins.assert_called_once()
    call_args = mock_add_coins.call_args
    assert call_args[0][0] == mock_db_session
    assert call_args[0][1] == game_id
    assert call_args[0][2] == user_id
    assert call_args[0][3] == 10  # first_blood reward
    assert call_args[0][4] == year
    assert call_args[0][5] == "achievement_first_blood"
    assert call_args[1]['auto_commit'] is False


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.add_coins')
def test_award_achievement_already_has(mock_add_coins, mock_db_session):
    """Test award_achievement returns None when user already has achievement."""
    # Setup
    game_id = 1
    user_id = 1
    achievement_code = "first_blood"
    year = 2024

    # Mock existing achievement
    existing_achievement = UserAchievement(
        id=1,
        game_id=game_id,
        user_id=user_id,
        achievement_code=achievement_code,
        year=year,
        period=None,
        earned_at=datetime.utcnow()
    )

    mock_result = MagicMock()
    mock_result.first.return_value = existing_achievement
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = award_achievement(mock_db_session, game_id, user_id, achievement_code, year)

    # Verify
    assert result is None
    mock_db_session.add.assert_not_called()
    mock_add_coins.assert_not_called()


@pytest.mark.unit
def test_get_current_win_streak_zero(mock_db_session):
    """Test get_current_win_streak returns 0 when no wins."""
    # Setup
    game_id = 1
    user_id = 1

    # Mock exec to return empty list (no wins)
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_current_win_streak(mock_db_session, game_id, user_id)

    # Verify
    assert result == 0


@pytest.mark.unit
def test_get_current_win_streak_three(mock_db_session):
    """Test get_current_win_streak returns 3 for three consecutive wins."""
    # Setup
    game_id = 1
    user_id = 1

    # Create mock results for 3 consecutive days
    results = [
        GameResult(id=3, game_id=game_id, winner_id=user_id, year=2024, day=170),  # Most recent
        GameResult(id=2, game_id=game_id, winner_id=user_id, year=2024, day=169),
        GameResult(id=1, game_id=game_id, winner_id=user_id, year=2024, day=168),
    ]

    # Mock exec to return results
    mock_result = MagicMock()
    mock_result.all.return_value = results
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_current_win_streak(mock_db_session, game_id, user_id)

    # Verify
    assert result == 3


@pytest.mark.unit
def test_get_current_win_streak_broken(mock_db_session):
    """Test get_current_win_streak stops at gap in wins."""
    # Setup
    game_id = 1
    user_id = 1

    # Create mock results with a gap (day 169 missing)
    results = [
        GameResult(id=3, game_id=game_id, winner_id=user_id, year=2024, day=171),  # Most recent
        GameResult(id=2, game_id=game_id, winner_id=user_id, year=2024, day=170),
        # Gap here - day 169 missing
        GameResult(id=1, game_id=game_id, winner_id=user_id, year=2024, day=168),
    ]

    # Mock exec to return results
    mock_result = MagicMock()
    mock_result.all.return_value = results
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_current_win_streak(mock_db_session, game_id, user_id)

    # Verify - streak should be 2 (days 171 and 170)
    assert result == 2


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.award_achievement')
def test_check_first_blood_awarded(mock_award_achievement, mock_db_session):
    """Test check_first_blood awards achievement on first win."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024

    # Mock no existing achievement
    mock_has_result = MagicMock()
    mock_has_result.first.return_value = None

    # Mock exactly 1 win
    mock_wins_result = MagicMock()
    mock_wins_result.all.return_value = [
        GameResult(id=1, game_id=game_id, winner_id=user_id, year=2024, day=170)
    ]

    # Configure exec to return different results
    call_count = [0]
    def exec_side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_has_result  # has_achievement check
        else:
            return mock_wins_result  # wins count check

    mock_db_session.exec.side_effect = exec_side_effect

    # Mock award_achievement to return achievement
    mock_achievement = UserAchievement(
        id=1,
        game_id=game_id,
        user_id=user_id,
        achievement_code="first_blood",
        year=year,
        period=None,
        earned_at=datetime.utcnow()
    )
    mock_award_achievement.return_value = mock_achievement

    # Execute
    result = check_first_blood(mock_db_session, game_id, user_id, year)

    # Verify
    assert result is not None
    mock_award_achievement.assert_called_once_with(
        mock_db_session, game_id, user_id, "first_blood", year
    )


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.award_achievement')
def test_check_first_blood_not_first(mock_award_achievement, mock_db_session):
    """Test check_first_blood doesn't award on second win."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024

    # Mock no existing achievement
    mock_has_result = MagicMock()
    mock_has_result.first.return_value = None

    # Mock 2 wins (not first)
    mock_wins_result = MagicMock()
    mock_wins_result.all.return_value = [
        GameResult(id=2, game_id=game_id, winner_id=user_id, year=2024, day=171),
        GameResult(id=1, game_id=game_id, winner_id=user_id, year=2024, day=170)
    ]

    # Configure exec to return different results
    call_count = [0]
    def exec_side_effect(stmt):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_has_result  # has_achievement check
        else:
            return mock_wins_result  # wins count check

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    result = check_first_blood(mock_db_session, game_id, user_id, year)

    # Verify
    assert result is None
    mock_award_achievement.assert_not_called()


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.get_current_win_streak')
@patch('bot.handlers.game.achievement_service.award_achievement')
def test_check_streak_3(mock_award_achievement, mock_get_streak, mock_db_session):
    """Test check_streak_achievements awards 'Снайпер' for 3 wins."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024

    # Mock streak of 3
    mock_get_streak.return_value = 3

    # Mock no existing achievements
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Mock award_achievement to return achievement
    mock_achievement = UserAchievement(
        id=1,
        game_id=game_id,
        user_id=user_id,
        achievement_code="streak_3",
        year=year,
        period=None,
        earned_at=datetime.utcnow()
    )
    mock_award_achievement.return_value = mock_achievement

    # Execute
    result = check_streak_achievements(mock_db_session, game_id, user_id, year)

    # Verify
    assert len(result) == 1
    assert result[0] == mock_achievement
    mock_award_achievement.assert_called_once_with(
        mock_db_session, game_id, user_id, "streak_3", year
    )


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.get_current_win_streak')
@patch('bot.handlers.game.achievement_service.award_achievement')
def test_check_streak_5(mock_award_achievement, mock_get_streak, mock_db_session):
    """Test check_streak_achievements awards 'Серия 5' for 5 wins."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024

    # Mock streak of 5
    mock_get_streak.return_value = 5

    # Mock no existing achievements
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Mock award_achievement to return achievements
    achievements = []
    def award_side_effect(db, gid, uid, code, y):
        achievement = UserAchievement(
            id=len(achievements) + 1,
            game_id=gid,
            user_id=uid,
            achievement_code=code,
            year=y,
            period=None,
            earned_at=datetime.utcnow()
        )
        achievements.append(achievement)
        return achievement

    mock_award_achievement.side_effect = award_side_effect

    # Execute
    result = check_streak_achievements(mock_db_session, game_id, user_id, year)

    # Verify - should award both streak_3 and streak_5
    assert len(result) == 2
    assert result[0].achievement_code == "streak_3"
    assert result[1].achievement_code == "streak_5"
    assert mock_award_achievement.call_count == 2


@pytest.mark.unit
@patch('bot.handlers.game.achievement_service.get_current_win_streak')
@patch('bot.handlers.game.achievement_service.award_achievement')
def test_check_streak_7(mock_award_achievement, mock_get_streak, mock_db_session):
    """Test check_streak_achievements awards 'Серия 7' for 7 wins."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024

    # Mock streak of 7
    mock_get_streak.return_value = 7

    # Mock no existing achievements
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Mock award_achievement to return achievements
    achievements = []
    def award_side_effect(db, gid, uid, code, y):
        achievement = UserAchievement(
            id=len(achievements) + 1,
            game_id=gid,
            user_id=uid,
            achievement_code=code,
            year=y,
            period=None,
            earned_at=datetime.utcnow()
        )
        achievements.append(achievement)
        return achievement

    mock_award_achievement.side_effect = award_side_effect

    # Execute
    result = check_streak_achievements(mock_db_session, game_id, user_id, year)

    # Verify - should award all three: streak_3, streak_5, and streak_7
    assert len(result) == 3
    assert result[0].achievement_code == "streak_3"
    assert result[1].achievement_code == "streak_5"
    assert result[2].achievement_code == "streak_7"
    assert mock_award_achievement.call_count == 3


@pytest.mark.unit
@patch('bot.handlers.game.config.get_config_by_game_id')
def test_check_and_award_achievements_disabled(mock_get_config, mock_db_session):
    """Test check_and_award_achievements returns empty list when disabled."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024
    day = 170

    # Mock config with achievements disabled
    mock_config = ChatConfig(
        chat_id=-123,
        enabled=True,
        is_test=False,
        constants=GameConstants(achievements_enabled=False)
    )
    mock_get_config.return_value = mock_config

    # Execute
    result = check_and_award_achievements(mock_db_session, game_id, user_id, year, day)

    # Verify - when disabled, should return empty list without checking achievements
    assert result == []
    assert len(result) == 0
