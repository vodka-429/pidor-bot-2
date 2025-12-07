"""Tests for missed days functionality."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from bot.handlers.game.commands import (
    get_missed_days_count,
    get_all_missed_days,
    get_dramatic_message,
    pidor_cmd,
    day_to_date
)
from bot.handlers.game.text_static import (
    MISSED_DAYS_1, MISSED_DAYS_2_3, MISSED_DAYS_4_7,
    MISSED_DAYS_8_14, MISSED_DAYS_15_30, MISSED_DAYS_31_PLUS
)


@pytest.mark.unit
def test_get_missed_days_count_no_previous_games(mock_context, mock_game):
    """Test missed days count when there are no previous games in the year."""
    # Setup: no previous games
    mock_context.db_session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
    
    # Execute: current day is 100, no previous games
    result = get_missed_days_count(mock_context.db_session, mock_game.id, 2024, 100)
    
    # Verify: should return current_day - 1 = 99
    assert result == 99


@pytest.mark.unit
def test_get_missed_days_count_one_day_missed(mock_context, mock_game):
    """Test missed days count when one day is missed."""
    # Setup: last game was on day 98
    mock_last_result = MagicMock()
    mock_last_result.day = 98
    mock_context.db_session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = mock_last_result
    
    # Execute: current day is 100
    result = get_missed_days_count(mock_context.db_session, mock_game.id, 2024, 100)
    
    # Verify: 100 - 98 - 1 = 1 day missed
    assert result == 1


@pytest.mark.unit
def test_get_missed_days_count_multiple_days_missed(mock_context, mock_game):
    """Test missed days count when multiple days are missed."""
    # Setup: last game was on day 90
    mock_last_result = MagicMock()
    mock_last_result.day = 90
    mock_context.db_session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = mock_last_result
    
    # Execute: current day is 100
    result = get_missed_days_count(mock_context.db_session, mock_game.id, 2024, 100)
    
    # Verify: 100 - 90 - 1 = 9 days missed
    assert result == 9


@pytest.mark.unit
def test_get_missed_days_count_no_days_missed(mock_context, mock_game):
    """Test missed days count when no days are missed (played yesterday)."""
    # Setup: last game was on day 99
    mock_last_result = MagicMock()
    mock_last_result.day = 99
    mock_context.db_session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = mock_last_result
    
    # Execute: current day is 100
    result = get_missed_days_count(mock_context.db_session, mock_game.id, 2024, 100)
    
    # Verify: 100 - 99 - 1 = 0 days missed
    assert result == 0


@pytest.mark.unit
def test_get_all_missed_days_no_games(mock_context, mock_game):
    """Test getting all missed days when there are no games in the year."""
    # Setup: no games played
    mock_context.db_session.query.return_value.filter_by.return_value.all.return_value = []
    
    # Execute: current day is 5
    result = get_all_missed_days(mock_context.db_session, mock_game.id, 2024, 5)
    
    # Verify: should return [1, 2, 3, 4]
    assert result == [1, 2, 3, 4]


@pytest.mark.unit
def test_get_all_missed_days_some_missed(mock_context, mock_game):
    """Test getting all missed days when some days are missed."""
    # Setup: games played on days 1, 3, 5
    mock_context.db_session.query.return_value.filter_by.return_value.all.return_value = [
        (1,), (3,), (5,)
    ]
    
    # Execute: current day is 7
    result = get_all_missed_days(mock_context.db_session, mock_game.id, 2024, 7)
    
    # Verify: should return [2, 4, 6] (days not played)
    assert result == [2, 4, 6]


@pytest.mark.unit
def test_get_all_missed_days_no_missed(mock_context, mock_game):
    """Test getting all missed days when no days are missed."""
    # Setup: games played on all days
    mock_context.db_session.query.return_value.filter_by.return_value.all.return_value = [
        (1,), (2,), (3,), (4,)
    ]
    
    # Execute: current day is 5
    result = get_all_missed_days(mock_context.db_session, mock_game.id, 2024, 5)
    
    # Verify: should return empty list
    assert result == []


@pytest.mark.unit
def test_get_dramatic_message_levels():
    """Test that correct dramatic message is returned for different day counts."""
    # Test level 1: 1 day
    assert get_dramatic_message(1) == MISSED_DAYS_1
    
    # Test level 2: 2-3 days
    msg_2 = get_dramatic_message(2)
    assert "{days}" not in msg_2  # Should be formatted
    assert "2" in msg_2
    
    msg_3 = get_dramatic_message(3)
    assert "3" in msg_3
    
    # Test level 3: 4-7 days
    msg_5 = get_dramatic_message(5)
    assert "5" in msg_5
    
    # Test level 4: 8-14 days
    msg_10 = get_dramatic_message(10)
    assert "10" in msg_10
    
    # Test level 5: 15-30 days
    msg_20 = get_dramatic_message(20)
    assert "20" in msg_20
    
    # Test level 6: 31+ days
    msg_50 = get_dramatic_message(50)
    assert "50" in msg_50


@pytest.mark.unit
def test_pidor_cmd_with_missed_days(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that pidor_cmd sends dramatic message when there are missed days."""
    # Setup: game with enough players
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain for Game (in decorator)
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock missed days check - last game was 5 days ago
    mock_last_result = MagicMock()
    mock_last_result.day = 162  # 5 days before current day 167
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = mock_last_result
    
    # Mock GameResult query - no result for today
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None
    
    # Setup query to return different results
    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]
    
    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        sample_players[0],  # winner
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
    ])
    
    # Mock time.sleep
    mocker.patch('bot.handlers.game.commands.time.sleep')
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidor_cmd(mock_update, mock_context)
    
    # Verify that 5 messages were sent (dramatic message + 4 stages)
    assert mock_update.effective_chat.send_message.call_count == 5
    
    # Verify that first message contains dramatic text about missed days
    first_call = mock_update.effective_chat.send_message.call_args_list[0]
    first_message = str(first_call)
    # Should contain "5" and some dramatic text
    assert "5" in first_message or "дней" in first_message or "days" in first_message


@pytest.mark.unit
def test_pidor_cmd_no_missed_days(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that pidor_cmd doesn't send dramatic message when there are no missed days."""
    # Setup: game with enough players
    mock_game.players = sample_players
    mock_context.game = mock_game
    
    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    
    # Mock missed days check - last game was yesterday (day 166)
    mock_last_result = MagicMock()
    mock_last_result.day = 166
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = mock_last_result
    
    # Mock GameResult query - no result for today
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None
    
    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]
    
    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        sample_players[0],
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
    ])
    
    # Mock time.sleep
    mocker.patch('bot.handlers.game.commands.time.sleep')
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    pidor_cmd(mock_update, mock_context)
    
    # Verify that only 4 messages were sent (no dramatic message, just 4 stages)
    assert mock_update.effective_chat.send_message.call_count == 4


@pytest.mark.unit
def test_day_to_date_conversion():
    """Test conversion of day number to date."""
    # Test day 1 (January 1)
    date1 = day_to_date(2024, 1)
    assert date1.month == 1
    assert date1.day == 1
    assert date1.year == 2024
    
    # Test day 32 (February 1)
    date32 = day_to_date(2024, 32)
    assert date32.month == 2
    assert date32.day == 1
    
    # Test day 366 (December 31 in leap year)
    date366 = day_to_date(2024, 366)
    assert date366.month == 12
    assert date366.day == 31


# Tests for /pidormissed command

@pytest.mark.unit
def test_pidormissed_cmd_no_missed_days(mock_update, mock_context, mock_game, mocker):
    """Test pidormissed command when there are no missed days."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game (in decorator)
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock get_all_missed_days to return empty list
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=[])
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.timetuple.return_value.tm_yday = 100
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    from bot.handlers.game.commands import pidormissed_cmd
    pidormissed_cmd(mock_update, mock_context)
    
    # Verify success message was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "не пропущено" in call_args or "Отличная работа" in call_args


@pytest.mark.unit
def test_pidormissed_cmd_few_missed_days(mock_update, mock_context, mock_game, mocker):
    """Test pidormissed command when there are few missed days (< 10)."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock get_all_missed_days to return 5 missed days
    missed_days = [1, 2, 5, 10, 15]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.timetuple.return_value.tm_yday = 100
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    from bot.handlers.game.commands import pidormissed_cmd
    pidormissed_cmd(mock_update, mock_context)
    
    # Verify message with list was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    # Should contain count and list
    assert "5" in call_args
    assert "Список" in call_args or "days_list" in call_args


@pytest.mark.unit
def test_pidormissed_cmd_many_missed_days(mock_update, mock_context, mock_game, mocker):
    """Test pidormissed command when there are many missed days (>= 10)."""
    # Setup
    mock_context.game = mock_game
    
    # Mock the query chain for Game
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Mock get_all_missed_days to return 15 missed days
    missed_days = list(range(1, 16))  # [1, 2, 3, ..., 15]
    mocker.patch('bot.handlers.game.commands.get_all_missed_days', return_value=missed_days)
    
    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.timetuple.return_value.tm_yday = 100
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)
    
    # Execute
    from bot.handlers.game.commands import pidormissed_cmd
    pidormissed_cmd(mock_update, mock_context)
    
    # Verify message with count only was sent (no list)
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    # Should contain count but not list
    assert "15" in call_args
    assert "Слишком много" in call_args or "много дней" in call_args
