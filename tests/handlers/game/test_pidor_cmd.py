"""Tests for pidor_cmd command."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, call, patch
from bot.handlers.game.commands import pidor_cmd
from bot.handlers.game.text_static import (
    ERROR_NOT_ENOUGH_PLAYERS,
    CURRENT_DAY_GAME_RESULT,
)
from bot.handlers.game.voting_helpers import get_player_weights, get_year_leaders


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidor_cmd_not_enough_players(mock_update, mock_context, mock_game):
    """Test that error is sent when there are less than 2 players."""
    # Setup: game with only 1 player
    mock_player = MagicMock()
    mock_game.players = [mock_player]
    mock_context.game = mock_game

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify
    mock_update.effective_chat.send_message.assert_called_once_with(ERROR_NOT_ENOUGH_PLAYERS)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidor_cmd_existing_result_today(mock_update, mock_context, mock_game, mocker):
    """Test that existing result message is sent when game was already played today."""
    # Setup: game with enough players
    mock_player1 = MagicMock()
    mock_player1.full_username.return_value = "@Player1"
    mock_player2 = MagicMock()
    mock_player2.full_username.return_value = "@Player2"

    mock_game.players = [mock_player1, mock_player2]
    mock_context.game = mock_game

    # Mock existing result for today
    mock_result = MagicMock()
    mock_result.winner = mock_player1
    mock_result.day = 167

    # Mock the query chain for Game (in decorator), missed days check, and GameResult (in function)
    # First call is for Game in ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Second call is for checking missed days (last result)
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = mock_result

    # Third call is for GameResult in pidor_cmd
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = mock_result

    # Setup query to return different results for Game, missed days, and GameResult
    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify that reply_markdown_v2 was called with the existing result message
    mock_update.message.reply_markdown_v2.assert_called_once()
    call_args = str(mock_update.message.reply_markdown_v2.call_args)
    assert "Player1" in call_args or CURRENT_DAY_GAME_RESULT[:20] in call_args


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidor_cmd_new_game_result(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that new game result is created and 4 stage messages are sent."""
    # Setup: game with enough players and no result for today
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock the query chain for Game (in decorator), missed days, and GameResult (in function)
    # First call is for Game in ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Second call is for checking missed days (no previous games)
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

    # Third call is for GameResult in pidor_cmd - should return None (no existing result)
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None

    # Setup query to return different results for Game, missed days, and GameResult
    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]

    # Mock random.choice to return first player and phrases
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        sample_players[0],  # winner selection
        "Stage 1 message",  # stage1 phrase
        "Stage 2 message",  # stage2 phrase
        "Stage 3 message",  # stage3 phrase
        "Stage 4 message: {username}",  # stage4 phrase
    ])

    # Mock asyncio.sleep to avoid delays
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Mock current_datetime to return a non-last-day date
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify that 5 messages were sent (dramatic message + stage1-4)
    # Since there are no previous games, missed_days = current_day - 1 = 167 - 1 = 166
    assert mock_update.effective_chat.send_message.call_count == 5

    # Verify that game result was appended
    mock_game.results.append.assert_called_once()

    # Verify that db session was committed
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidor_cmd_last_day_of_year(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that year results announcement is sent on December 31."""
    # Setup: game with enough players
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Mock missed days check
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

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

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Mock current_datetime to return December 31
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 31
    mock_dt.timetuple.return_value.tm_yday = 366
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock get_player_weights to return single leader (no tie-breaker needed)
    mock_player_weights = [
        (sample_players[0], 5),
        (sample_players[1], 3),
        (sample_players[2], 2),
    ]
    mocker.patch('bot.handlers.game.commands.get_player_weights', return_value=mock_player_weights)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify that 6 messages were sent (dramatic message + year announcement + 4 stages)
    # Since there are no previous games, missed_days = current_day - 1 = 366 - 1 = 365
    assert mock_update.effective_chat.send_message.call_count == 6

    # Verify year announcement was sent (it's the second message, after dramatic message)
    calls = mock_update.effective_chat.send_message.call_args_list
    second_call_str = str(calls[1])
    assert "2024" in second_call_str or "Новым Годом" in second_call_str


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidor_cmd_random_winner_selection(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that winner is randomly selected from players list."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Mock missed days check
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None

    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]

    # Mock random.choice and capture the call
    mock_random_choice = mocker.patch('bot.handlers.game.commands.random.choice')
    mock_random_choice.side_effect = [
        sample_players[1],  # winner
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
    ]

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify random.choice was called with players list
    assert mock_random_choice.call_count >= 1
    first_call_args = mock_random_choice.call_args_list[0][0]
    assert first_call_args[0] == sample_players


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidor_cmd_time_delays(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that time delays are called between messages."""
    # Setup
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Mock missed days check
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

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

    # Mock asyncio.sleep and capture calls
    mock_sleep = mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Mock current_datetime
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify asyncio.sleep was called 4 times with GAME_RESULT_TIME_DELAY (2 seconds)
    # 1 for dramatic message + 3 for stages
    assert mock_sleep.call_count == 4
    for call in mock_sleep.call_args_list:
        assert call[0][0] == 2  # GAME_RESULT_TIME_DELAY


# Integration tests for get_player_weights + get_year_leaders combination


@pytest.mark.unit
def test_get_year_leaders_integration_single_leader(mock_db_session, mock_game, sample_players):
    """Test get_year_leaders integration with single leader."""
    # Setup: Create mock results with one clear leader
    # Player 1: 5 wins, Player 2: 3 wins, Player 3: 2 wins
    mock_results = [
        (sample_players[0], 5),
        (sample_players[1], 3),
        (sample_players[2], 2),
    ]

    # Mock db_session.exec to return mock results
    mock_db_session.exec.return_value.all.return_value = mock_results

    # Execute: Get player weights and then leaders
    player_weights = get_player_weights(mock_db_session, mock_game.id, 2024)
    year_leaders = get_year_leaders(player_weights)

    # Verify: Only one leader with 5 wins
    assert len(year_leaders) == 1
    assert year_leaders[0][0] == sample_players[0]
    assert year_leaders[0][1] == 5


@pytest.mark.unit
def test_get_year_leaders_integration_multiple_leaders(mock_db_session, mock_game, sample_players):
    """Test get_year_leaders integration with multiple leaders."""
    # Setup: Create mock results with two leaders having same score
    # Player 1: 5 wins, Player 2: 5 wins, Player 3: 2 wins
    mock_results = [
        (sample_players[0], 5),
        (sample_players[1], 5),
        (sample_players[2], 2),
    ]

    # Mock db_session.exec to return mock results
    mock_db_session.exec.return_value.all.return_value = mock_results

    # Execute: Get player weights and then leaders
    player_weights = get_player_weights(mock_db_session, mock_game.id, 2024)
    year_leaders = get_year_leaders(player_weights)

    # Verify: Two leaders with 5 wins each
    assert len(year_leaders) == 2
    assert year_leaders[0][0] == sample_players[0]
    assert year_leaders[0][1] == 5
    assert year_leaders[1][0] == sample_players[1]
    assert year_leaders[1][1] == 5


@pytest.mark.unit
def test_get_year_leaders_integration_no_results(mock_db_session, mock_game):
    """Test get_year_leaders integration with no results in year."""
    # Setup: No results for the year
    mock_db_session.exec.return_value.all.return_value = []

    # Execute: Get player weights and then leaders
    player_weights = get_player_weights(mock_db_session, mock_game.id, 2024)
    year_leaders = get_year_leaders(player_weights)

    # Verify: No leaders
    assert len(year_leaders) == 0


# Tests for run_tiebreaker function


@pytest.mark.asyncio
@pytest.mark.unit
async def test_run_tiebreaker_two_leaders(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test tie-breaker between two leaders."""
    from bot.handlers.game.commands import run_tiebreaker

    # Setup: Two leaders
    leaders = [sample_players[0], sample_players[1]]
    year = 2024

    mock_context.game = mock_game

    # Mock random.choice to return first leader
    mock_random = mocker.patch('bot.handlers.game.commands.random.choice', return_value=leaders[0])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Execute
    await run_tiebreaker(mock_update, mock_context, leaders, year)

    # Verify: random.choice was called with leaders
    mock_random.assert_called_once_with(leaders)

    # Verify: Two messages were sent (announcement + result)
    assert mock_update.effective_chat.send_message.call_count == 2

    # Verify: GameResult was created
    mock_game.results.append.assert_called_once()

    # Verify: DB session was committed
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_run_tiebreaker_three_leaders(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test tie-breaker between three leaders."""
    from bot.handlers.game.commands import run_tiebreaker

    # Setup: Three leaders
    leaders = sample_players  # All three players
    year = 2024

    mock_context.game = mock_game

    # Mock random.choice to return second leader
    mock_random = mocker.patch('bot.handlers.game.commands.random.choice', return_value=leaders[1])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Execute
    await run_tiebreaker(mock_update, mock_context, leaders, year)

    # Verify: random.choice was called with all three leaders
    mock_random.assert_called_once_with(leaders)

    # Verify: Two messages were sent
    assert mock_update.effective_chat.send_message.call_count == 2

    # Verify: Winner is the second leader
    call_args = mock_game.results.append.call_args[0][0]
    assert call_args.winner == leaders[1]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_run_tiebreaker_creates_game_result(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that tie-breaker creates GameResult with correct day number."""
    from bot.handlers.game.commands import run_tiebreaker
    from bot.app.models import GameResult

    # Setup
    leaders = [sample_players[0], sample_players[1]]
    year = 2023  # Not a leap year

    mock_context.game = mock_game

    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', return_value=leaders[0])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Execute
    await run_tiebreaker(mock_update, mock_context, leaders, year)

    # Verify: GameResult was created with day 366 (non-leap year)
    call_args = mock_game.results.append.call_args[0][0]
    assert isinstance(call_args, GameResult)
    assert call_args.game_id == mock_game.id
    assert call_args.year == year
    assert call_args.day == 366  # Special day for non-leap year
    assert call_args.winner == leaders[0]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_run_tiebreaker_leap_year(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that tie-breaker uses day 367 for leap year."""
    from bot.handlers.game.commands import run_tiebreaker

    # Setup
    leaders = [sample_players[0], sample_players[1]]
    year = 2024  # Leap year

    mock_context.game = mock_game

    # Mock random.choice
    mocker.patch('bot.handlers.game.commands.random.choice', return_value=leaders[0])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Execute
    await run_tiebreaker(mock_update, mock_context, leaders, year)

    # Verify: GameResult was created with day 367 (leap year)
    call_args = mock_game.results.append.call_args[0][0]
    assert call_args.day == 367  # Special day for leap year


# Tests for pidor_cmd with tie-breaker integration


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidor_cmd_last_day_triggers_tiebreaker(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that tie-breaker is triggered on last day when multiple leaders exist."""
    # Setup: game with enough players
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Mock missed days check
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None

    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]

    # Mock random.choice for winner selection and phrases
    mocker.patch('bot.handlers.game.commands.random.choice', side_effect=[
        sample_players[0],  # winner of main draw
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
        sample_players[1],  # winner of tie-breaker
    ])

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Mock current_datetime to return December 31
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 31
    mock_dt.timetuple.return_value.tm_yday = 366
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock get_player_weights to return two leaders with same score
    mock_player_weights = [
        (sample_players[0], 5),
        (sample_players[1], 5),
        (sample_players[2], 3),
    ]
    mocker.patch('bot.handlers.game.commands.get_player_weights', return_value=mock_player_weights)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify: 8 messages were sent (dramatic + year announcement + 4 stages + tie-breaker announcement + tie-breaker result)
    # Since there are no previous games, missed_days = current_day - 1 = 366 - 1 = 365
    assert mock_update.effective_chat.send_message.call_count == 8

    # Verify: Two GameResults were created (main draw + tie-breaker)
    assert mock_game.results.append.call_count == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidor_cmd_last_day_single_leader_no_tiebreaker(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that tie-breaker is NOT triggered when there's only one leader."""
    # Setup: game with enough players
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Mock missed days check
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

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

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Mock current_datetime to return December 31
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 12
    mock_dt.day = 31
    mock_dt.timetuple.return_value.tm_yday = 366
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Mock get_player_weights to return single leader
    mock_player_weights = [
        (sample_players[0], 5),
        (sample_players[1], 3),
        (sample_players[2], 2),
    ]
    mocker.patch('bot.handlers.game.commands.get_player_weights', return_value=mock_player_weights)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify: 6 messages were sent (dramatic + year announcement + 4 stages, NO tie-breaker)
    assert mock_update.effective_chat.send_message.call_count == 6

    # Verify: Only one GameResult was created (main draw only)
    assert mock_game.results.append.call_count == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_pidor_cmd_not_last_day_no_tiebreaker(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test that tie-breaker is NOT triggered on regular days."""
    # Setup: game with enough players
    mock_game.players = sample_players
    mock_context.game = mock_game

    # Mock the query chain
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Mock missed days check
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

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

    # Mock asyncio.sleep
    mocker.patch('bot.handlers.game.commands.asyncio.sleep')

    # Mock current_datetime to return a regular day (NOT December 31)
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify: 5 messages were sent (dramatic + 4 stages, NO year announcement, NO tie-breaker)
    assert mock_update.effective_chat.send_message.call_count == 5

    # Verify: Only one GameResult was created (main draw only)
    assert mock_game.results.append.call_count == 1
