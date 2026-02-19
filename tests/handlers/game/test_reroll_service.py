"""Tests for reroll service functionality."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, date

from bot.handlers.game.reroll_service import (
    can_reroll,
    execute_reroll,
    remove_reroll_button_after_timeout
)
from bot.handlers.game.config import GameConstants
from bot.app.models import GameResult, TGUser

# Используем значения по умолчанию из конфигурации
_default_constants = GameConstants()
REROLL_PRICE = _default_constants.reroll_price
COINS_PER_WIN = _default_constants.coins_per_win


@pytest.mark.unit
def test_can_reroll_returns_true_when_available(mock_db_session):
    """Test can_reroll returns True when reroll is available."""
    # Setup
    game_id = 1
    year = 2024
    day = 100

    # Mock GameResult with reroll available
    mock_game_result = MagicMock()
    mock_game_result.reroll_available = True

    mock_result = MagicMock()
    mock_result.first.return_value = mock_game_result
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = can_reroll(mock_db_session, game_id, year, day)

    # Verify
    assert result is True
    mock_db_session.exec.assert_called_once()


@pytest.mark.unit
def test_can_reroll_returns_false_when_not_available(mock_db_session):
    """Test can_reroll returns False when reroll is not available."""
    # Setup
    game_id = 1
    year = 2024
    day = 100

    # Mock GameResult with reroll not available
    mock_game_result = MagicMock()
    mock_game_result.reroll_available = False

    mock_result = MagicMock()
    mock_result.first.return_value = mock_game_result
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = can_reroll(mock_db_session, game_id, year, day)

    # Verify
    assert result is False


@pytest.mark.unit
def test_can_reroll_returns_false_when_game_result_not_found(mock_db_session):
    """Test can_reroll returns False when GameResult doesn't exist."""
    # Setup
    game_id = 1
    year = 2024
    day = 100

    # Mock no GameResult found
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = can_reroll(mock_db_session, game_id, year, day)

    # Verify
    assert result is False


@pytest.mark.unit
def test_execute_reroll_updates_game_result(mock_db_session, sample_players):
    """Test execute_reroll updates GameResult with new winner."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id
    mock_game_result.reroll_available = True

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        # First call - get GameResult
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            # Second call - get old winner
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    current_date = date(2024, 4, 10)  # День 100 в 2024 году

    with patch('bot.handlers.game.reroll_service.get_config_by_game_id') as mock_get_config, \
         patch('bot.handlers.game.reroll_service.spend_coins') as mock_spend, \
         patch('bot.handlers.game.reroll_service.add_coins') as mock_add, \
         patch('bot.handlers.game.selection_service.select_winner_with_effects') as mock_select:

        # Мокаем конфигурацию
        mock_config = MagicMock()
        mock_config.constants.reroll_enabled = True
        mock_config.constants.reroll_price = REROLL_PRICE
        mock_config.constants.coins_per_win = COINS_PER_WIN
        mock_get_config.return_value = mock_config

        # Мокаем результат выбора победителя
        mock_selection_result = MagicMock()
        mock_selection_result.winner = sample_players[1]
        mock_selection_result.all_protected = False
        mock_selection_result.had_immunity = False
        mock_selection_result.protected_player = None
        mock_select.return_value = mock_selection_result

        old_winner_result, new_winner_result, selection_result = execute_reroll(
            mock_db_session, game_id, year, day, initiator_id, sample_players, current_date
        )

    # Verify get_config_by_game_id was called
    mock_get_config.assert_called_once_with(mock_db_session, game_id)

    # Verify spend_coins was called
    mock_spend.assert_called_once_with(
        mock_db_session, game_id, initiator_id, REROLL_PRICE, year, "reroll", auto_commit=False
    )

    # Verify add_coins was called for new winner
    mock_add.assert_called_once_with(
        mock_db_session, game_id, sample_players[1].id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify GameResult was updated
    assert mock_game_result.original_winner_id == old_winner_id
    assert mock_game_result.winner_id == sample_players[1].id
    assert mock_game_result.reroll_available is False
    assert mock_game_result.reroll_initiator_id == initiator_id

    # Verify commit was called
    mock_db_session.commit.assert_called_once()

    # Verify returned values
    assert old_winner_result == old_winner
    assert new_winner_result == sample_players[1]


@pytest.mark.unit
def test_execute_reroll_allows_same_winner(mock_db_session, sample_players):
    """Test execute_reroll allows the same person to win again (double reward)."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute - same player wins again
    current_date = date(2024, 4, 10)

    with patch('bot.handlers.game.reroll_service.get_config_by_game_id') as mock_get_config, \
         patch('bot.handlers.game.reroll_service.spend_coins'), \
         patch('bot.handlers.game.reroll_service.add_coins') as mock_add, \
         patch('bot.handlers.game.selection_service.select_winner_with_effects') as mock_select:

        # Мокаем конфигурацию
        mock_config = MagicMock()
        mock_config.constants.reroll_enabled = True
        mock_config.constants.reroll_price = REROLL_PRICE
        mock_config.constants.coins_per_win = COINS_PER_WIN
        mock_get_config.return_value = mock_config

        # Мокаем результат выбора победителя - тот же игрок
        mock_selection_result = MagicMock()
        mock_selection_result.winner = old_winner
        mock_selection_result.all_protected = False
        mock_selection_result.had_immunity = False
        mock_selection_result.protected_player = None
        mock_select.return_value = mock_selection_result

        old_winner_result, new_winner_result, selection_result = execute_reroll(
            mock_db_session, game_id, year, day, initiator_id, sample_players, current_date
        )

    # Verify add_coins was called even for the same winner (double reward)
    mock_add.assert_called_once_with(
        mock_db_session, game_id, old_winner.id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify both returned winners are the same
    assert old_winner_result == old_winner
    assert new_winner_result == old_winner


@pytest.mark.unit
def test_execute_reroll_raises_error_when_no_players(mock_db_session):
    """Test execute_reroll raises ValueError when players list is empty."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    players = []

    # Execute and verify
    current_date = date(2024, 4, 10)
    with pytest.raises(ValueError, match="Players list cannot be empty"):
        execute_reroll(mock_db_session, game_id, year, day, initiator_id, players, current_date)


@pytest.mark.unit
def test_execute_reroll_raises_error_when_game_result_not_found(mock_db_session, sample_players):
    """Test execute_reroll raises ValueError when GameResult doesn't exist."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2

    # Mock no GameResult found
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Execute and verify
    current_date = date(2024, 4, 10)
    with patch('bot.handlers.game.reroll_service.get_config_by_game_id') as mock_get_config:
        # Мокаем конфигурацию
        mock_config = MagicMock()
        mock_config.constants.reroll_enabled = True
        mock_get_config.return_value = mock_config

        with pytest.raises(ValueError, match="GameResult not found"):
            execute_reroll(mock_db_session, game_id, year, day, initiator_id, sample_players, current_date)


@pytest.mark.unit
def test_execute_reroll_raises_error_when_old_winner_not_found(mock_db_session, sample_players):
    """Test execute_reroll raises ValueError when old winner doesn't exist."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 999  # Non-existent user

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            # Old winner not found
            mock_result.first.return_value = None

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute and verify
    current_date = date(2024, 4, 10)
    with patch('bot.handlers.game.reroll_service.get_config_by_game_id') as mock_get_config:
        # Мокаем конфигурацию
        mock_config = MagicMock()
        mock_config.constants.reroll_enabled = True
        mock_get_config.return_value = mock_config

        with pytest.raises(ValueError, match="Old winner with id .* not found"):
            execute_reroll(mock_db_session, game_id, year, day, initiator_id, sample_players, current_date)


@pytest.mark.asyncio
async def test_remove_reroll_button_after_timeout_removes_button():
    """Test remove_reroll_button_after_timeout removes button after delay."""
    # Setup
    mock_bot = MagicMock()
    mock_bot.edit_message_reply_markup = AsyncMock()
    chat_id = 123456
    message_id = 789
    delay_minutes = 0.001  # Very short delay for testing

    # Execute
    await remove_reroll_button_after_timeout(mock_bot, chat_id, message_id, delay_minutes)

    # Verify
    mock_bot.edit_message_reply_markup.assert_called_once_with(
        chat_id=chat_id,
        message_id=message_id,
        reply_markup=None
    )


@pytest.mark.asyncio
async def test_remove_reroll_button_handles_exception():
    """Test remove_reroll_button_after_timeout handles exceptions gracefully."""
    # Setup
    mock_bot = MagicMock()
    mock_bot.edit_message_reply_markup = AsyncMock(side_effect=Exception("Message deleted"))
    chat_id = 123456
    message_id = 789
    delay_minutes = 0.001

    # Execute - should not raise exception
    await remove_reroll_button_after_timeout(mock_bot, chat_id, message_id, delay_minutes)

    # Verify the call was attempted
    mock_bot.edit_message_reply_markup.assert_called_once()


@pytest.mark.unit
def test_execute_reroll_preserves_old_winner_coins(mock_db_session, sample_players):
    """Test execute_reroll does NOT remove coins from old winner."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    current_date = date(2024, 4, 10)

    with patch('bot.handlers.game.reroll_service.get_config_by_game_id') as mock_get_config, \
         patch('bot.handlers.game.reroll_service.spend_coins') as mock_spend, \
         patch('bot.handlers.game.reroll_service.add_coins') as mock_add, \
         patch('bot.handlers.game.selection_service.select_winner_with_effects') as mock_select:

        # Мокаем конфигурацию
        mock_config = MagicMock()
        mock_config.constants.reroll_enabled = True
        mock_config.constants.reroll_price = REROLL_PRICE
        mock_config.constants.coins_per_win = COINS_PER_WIN
        mock_get_config.return_value = mock_config

        # Мокаем результат выбора победителя
        mock_selection_result = MagicMock()
        mock_selection_result.winner = sample_players[1]
        mock_selection_result.all_protected = False
        mock_selection_result.had_immunity = False
        mock_selection_result.protected_player = None
        mock_select.return_value = mock_selection_result

        _, _, _ = execute_reroll(mock_db_session, game_id, year, day, initiator_id, sample_players, current_date)

    # Verify spend_coins was called ONLY for initiator, NOT for old winner
    assert mock_spend.call_count == 1
    mock_spend.assert_called_with(
        mock_db_session, game_id, initiator_id, REROLL_PRICE, year, "reroll", auto_commit=False
    )

    # Verify add_coins was called ONLY for new winner
    assert mock_add.call_count == 1
    mock_add.assert_called_with(
        mock_db_session, game_id, sample_players[1].id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )


@pytest.mark.unit
def test_execute_reroll_with_immunity_protection(mock_db_session, sample_players):
    """Test execute_reroll respects immunity - protected player is not selected."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Protected player (будет выбран первым, но защищён)
    protected_player = sample_players[1]
    protected_player.id = 2

    # Final winner (будет выбран после перевыбора)
    final_winner = sample_players[2]
    final_winner.id = 3

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    current_date = date(2024, 4, 10)

    with patch('bot.handlers.game.reroll_service.get_config_by_game_id') as mock_get_config, \
         patch('bot.handlers.game.reroll_service.spend_coins') as mock_spend, \
         patch('bot.handlers.game.reroll_service.add_coins') as mock_add, \
         patch('bot.handlers.game.selection_service.select_winner_with_effects') as mock_select:

        # Мокаем конфигурацию
        mock_config = MagicMock()
        mock_config.constants.reroll_enabled = True
        mock_config.constants.reroll_price = REROLL_PRICE
        mock_config.constants.coins_per_win = COINS_PER_WIN
        mock_get_config.return_value = mock_config

        # Мокаем результат выбора: защита сработала, перевыбран другой игрок
        mock_selection_result = MagicMock()
        mock_selection_result.winner = final_winner
        mock_selection_result.all_protected = False
        mock_selection_result.had_immunity = True  # Защита сработала!
        mock_selection_result.protected_player = protected_player
        mock_select.return_value = mock_selection_result

        old_winner_result, new_winner_result, selection_result = execute_reroll(
            mock_db_session, game_id, year, day, initiator_id, sample_players, current_date
        )

    # Verify selection was called with correct parameters
    mock_select.assert_called_once_with(
        mock_db_session, game_id, sample_players, current_date, True
    )

    # Verify coins were added to protected player (immunity reward)
    assert mock_add.call_count == 2
    # First call - immunity reward for protected player
    mock_add.assert_any_call(
        mock_db_session, game_id, protected_player.id, COINS_PER_WIN, year, "immunity_save_reroll", auto_commit=False
    )
    # Second call - win reward for final winner
    mock_add.assert_any_call(
        mock_db_session, game_id, final_winner.id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify GameResult was updated with final winner
    assert mock_game_result.winner_id == final_winner.id

    # Verify returned values
    assert old_winner_result == old_winner
    assert new_winner_result == final_winner


@pytest.mark.unit
def test_execute_reroll_with_double_chance(mock_db_session, sample_players):
    """Test execute_reroll respects double chance - player appears twice in pool."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Winner with double chance
    double_chance_winner = sample_players[1]
    double_chance_winner.id = 2

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    current_date = date(2024, 4, 10)

    with patch('bot.handlers.game.reroll_service.get_config_by_game_id') as mock_get_config, \
         patch('bot.handlers.game.reroll_service.spend_coins') as mock_spend, \
         patch('bot.handlers.game.reroll_service.add_coins') as mock_add, \
         patch('bot.handlers.game.selection_service.select_winner_with_effects') as mock_select:

        # Мокаем конфигурацию
        mock_config = MagicMock()
        mock_config.constants.reroll_enabled = True
        mock_config.constants.reroll_price = REROLL_PRICE
        mock_config.constants.coins_per_win = COINS_PER_WIN
        mock_get_config.return_value = mock_config

        # Мокаем результат выбора: победитель с двойным шансом
        mock_selection_result = MagicMock()
        mock_selection_result.winner = double_chance_winner
        mock_selection_result.all_protected = False
        mock_selection_result.had_immunity = False
        mock_selection_result.had_double_chance = True  # Двойной шанс сработал!
        mock_selection_result.protected_player = None
        mock_select.return_value = mock_selection_result

        old_winner_result, new_winner_result, selection_result = execute_reroll(
            mock_db_session, game_id, year, day, initiator_id, sample_players, current_date
        )

    # Verify selection was called (it handles double chance internally)
    mock_select.assert_called_once_with(
        mock_db_session, game_id, sample_players, current_date, True
    )

    # Verify coins were added to winner
    assert mock_add.call_count == 1
    mock_add.assert_called_with(
        mock_db_session, game_id, double_chance_winner.id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify GameResult was updated
    assert mock_game_result.winner_id == double_chance_winner.id

    # Verify returned values
    assert old_winner_result == old_winner
    assert new_winner_result == double_chance_winner

    # Verify selection_result contains correct double_chance flag
    assert selection_result.had_double_chance is True
    assert selection_result.winner == double_chance_winner


@pytest.mark.unit
def test_execute_reroll_when_all_protected(mock_db_session, sample_players):
    """Test execute_reroll when all players are protected - selects random player."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Random winner (будет выбран случайно, т.к. все защищены)
    random_winner = sample_players[1]

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    current_date = date(2024, 4, 10)

    with patch('bot.handlers.game.reroll_service.get_config_by_game_id') as mock_get_config, \
         patch('bot.handlers.game.reroll_service.spend_coins') as mock_spend, \
         patch('bot.handlers.game.reroll_service.add_coins') as mock_add, \
         patch('bot.handlers.game.selection_service.select_winner_with_effects') as mock_select, \
         patch('random.choice', return_value=random_winner) as mock_random:

        # Мокаем конфигурацию
        mock_config = MagicMock()
        mock_config.constants.reroll_enabled = True
        mock_config.constants.reroll_price = REROLL_PRICE
        mock_config.constants.coins_per_win = COINS_PER_WIN
        mock_get_config.return_value = mock_config

        # Мокаем результат выбора: все защищены
        mock_selection_result = MagicMock()
        mock_selection_result.winner = None  # Нет победителя
        mock_selection_result.all_protected = True  # Все защищены!
        mock_selection_result.had_immunity = False
        mock_selection_result.protected_player = None
        mock_select.return_value = mock_selection_result

        old_winner_result, new_winner_result, selection_result = execute_reroll(
            mock_db_session, game_id, year, day, initiator_id, sample_players, current_date
        )

    # Verify selection was called
    mock_select.assert_called_once_with(
        mock_db_session, game_id, sample_players, current_date, True
    )

    # Verify random.choice was called as fallback
    mock_random.assert_called_once_with(sample_players)

    # Verify coins were added to random winner
    assert mock_add.call_count == 1
    mock_add.assert_called_with(
        mock_db_session, game_id, random_winner.id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify GameResult was updated with random winner
    assert mock_game_result.winner_id == random_winner.id

    # Verify returned values
    assert old_winner_result == old_winner
    assert new_winner_result == random_winner


@pytest.mark.unit
def test_reroll_returns_correct_selection_result(mock_db_session, sample_players):
    """Test execute_reroll returns SelectionResult that matches the actual winner."""
    # Setup
    game_id = 1
    year = 2024
    day = 100
    initiator_id = 2
    old_winner_id = 1

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner_id

    # Mock old winner
    old_winner = sample_players[0]
    old_winner.id = old_winner_id

    # Winner with double chance
    double_chance_winner = sample_players[1]
    double_chance_winner.id = 2

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            mock_result.first.return_value = old_winner

        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    current_date = date(2024, 4, 10)

    with patch('bot.handlers.game.reroll_service.get_config_by_game_id') as mock_get_config, \
         patch('bot.handlers.game.reroll_service.spend_coins'), \
         patch('bot.handlers.game.reroll_service.add_coins'), \
         patch('bot.handlers.game.selection_service.select_winner_with_effects') as mock_select:

        # Мокаем конфигурацию
        mock_config = MagicMock()
        mock_config.constants.reroll_enabled = True
        mock_config.constants.reroll_price = REROLL_PRICE
        mock_config.constants.coins_per_win = COINS_PER_WIN
        mock_get_config.return_value = mock_config

        # Мокаем результат выбора: победитель с двойным шансом
        mock_selection_result = MagicMock()
        mock_selection_result.winner = double_chance_winner
        mock_selection_result.all_protected = False
        mock_selection_result.had_immunity = False
        mock_selection_result.had_double_chance = True  # Двойной шанс сработал!
        mock_selection_result.protected_player = None
        mock_select.return_value = mock_selection_result

        old_winner_result, new_winner_result, selection_result = execute_reroll(
            mock_db_session, game_id, year, day, initiator_id, sample_players, current_date
        )

    # Verify selection_result matches the actual winner
    assert selection_result.winner == new_winner_result, \
        "SelectionResult.winner should match new_winner"
    assert selection_result.winner == double_chance_winner, \
        "SelectionResult.winner should be the double_chance_winner"

    # Verify selection_result.had_double_chance corresponds to the actual winner
    assert selection_result.had_double_chance is True, \
        "SelectionResult.had_double_chance should be True for double_chance_winner"

    # Verify selection_result.had_immunity is correct
    assert selection_result.had_immunity is False, \
        "SelectionResult.had_immunity should be False when no immunity triggered"

    # Verify selection_result.all_protected is correct
    assert selection_result.all_protected is False, \
        "SelectionResult.all_protected should be False when winner was selected"

    # Verify selection_result.protected_player is None when no immunity
    assert selection_result.protected_player is None, \
        "SelectionResult.protected_player should be None when no immunity triggered"
