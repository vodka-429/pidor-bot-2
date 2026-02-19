"""Integration tests for game handlers."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, call, AsyncMock

from bot.handlers.game.commands import pidor_cmd, pidoreg_cmd, pidorstats_cmd
from bot.handlers.game.config import GameConstants

# Константы для тестов
_default_constants = GameConstants()
COINS_PER_WIN = _default_constants.coins_per_win
PREDICTION_REWARD = _default_constants.prediction_reward
REROLL_PRICE = _default_constants.reroll_price


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_game_flow(mock_update, mock_context, mock_game, sample_players, mocker):
    """Test full game flow: registration -> game -> stats."""
    # Mock asyncio.sleep to avoid delays
    mocker.patch('asyncio.sleep', new_callable=AsyncMock)

    # Mock random.choice to return first player
    mock_choice = mocker.patch('bot.handlers.game.commands.random.choice')
    mock_choice.return_value = sample_players[0]

    # Mock datetime to return a specific date
    mock_dt = MagicMock()
    mock_dt.year = 2024
    mock_dt.month = 6
    mock_dt.day = 15
    mock_dt.timetuple.return_value.tm_yday = 167
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Setup game with no players initially
    mock_game.players = []
    mock_context.game = mock_game

    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game

    # Step 1: Register first player
    mock_context.tg_user = sample_players[0]
    mock_context.db_session.query.return_value = mock_game_query

    await pidoreg_cmd(mock_update, mock_context)

    # Verify first player registration
    assert sample_players[0] in mock_game.players
    assert mock_update.effective_message.reply_markdown_v2.call_count >= 1

    # Step 2: Register second player
    mock_context.tg_user = sample_players[1]
    mock_update.effective_message.reply_markdown_v2.reset_mock()

    await pidoreg_cmd(mock_update, mock_context)

    # Verify second player registration
    assert sample_players[1] in mock_game.players

    # Step 3: Register third player
    mock_context.tg_user = sample_players[2]
    mock_update.effective_message.reply_markdown_v2.reset_mock()

    await pidoreg_cmd(mock_update, mock_context)

    # Verify third player registration
    assert sample_players[2] in mock_game.players
    assert len(mock_game.players) == 3

    # Reset mocks for game command
    mock_update.effective_chat.send_message.reset_mock()

    # Mock query for checking missed days (no previous games)
    mock_missed_query = MagicMock()
    mock_missed_query.filter_by.return_value = mock_missed_query
    mock_missed_query.order_by.return_value = mock_missed_query
    mock_missed_query.first.return_value = None

    # Mock GameResult query to return None (no existing result)
    mock_result_query = MagicMock()
    mock_result_query.filter_by.return_value = mock_result_query
    mock_result_query.one_or_none.return_value = None

    # Setup query to return different results for Game, missed days check, and GameResult
    mock_context.db_session.query.side_effect = [mock_game_query, mock_missed_query, mock_result_query]

    # Mock random.choice for stage phrases
    mock_choice.side_effect = [
        sample_players[0],  # winner
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
    ]

    # Mock send_result_with_reroll_button
    mocker.patch('bot.handlers.game.commands.send_result_with_reroll_button', new_callable=AsyncMock)

    # Step 4: Run the game
    await pidor_cmd(mock_update, mock_context)

    # Verify game execution - should send 4 messages (dramatic message + 3 stage messages)
    # Stage 4 is now sent via send_result_with_reroll_button, not send_message
    # Since there are no previous games, missed_days = current_day - 1 = 167 - 1 = 166
    assert mock_update.effective_chat.send_message.call_count == 4

    # Verify GameResult was created
    assert mock_game.results.append.called
    assert mock_context.db_session.commit.called

    # Reset mocks for stats command
    mock_update.effective_chat.send_message.reset_mock()

    # Setup mock for stats query
    mock_stats_result = MagicMock()
    mock_stats_data = [
        (sample_players[0], 5),
        (sample_players[1], 3),
        (sample_players[2], 2),
    ]
    mock_stats_result.all.return_value = mock_stats_data
    mock_context.db_session.exec.return_value = mock_stats_result

    # Reset query side_effect for stats command
    mock_context.db_session.query.side_effect = None
    mock_context.db_session.query.return_value = mock_game_query

    # Step 5: Check stats
    await pidorstats_cmd(mock_update, mock_context)

    # Verify stats were displayed
    assert mock_update.effective_chat.send_message.called
    call_args = mock_update.effective_chat.send_message.call_args
    assert call_args is not None

    # Verify the message contains player information
    message_text = str(call_args)
    assert 'player_count=3' in message_text or '3' in message_text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reroll_with_immunity_protection(mock_update, mock_context, mock_game, sample_players, mocker):
    """Integration test: full scenario with immunity protection during reroll."""
    from datetime import date
    from bot.handlers.game.reroll_service import execute_reroll

    # Setup
    game_id = 1
    year = 2024
    day = 100
    current_date = date(2024, 4, 10)  # День 100 в 2024 году

    # Игроки: [0] - старый победитель, [1] - защищённый, [2] - новый победитель
    old_winner = sample_players[0]
    old_winner.id = 1
    protected_player = sample_players[1]
    protected_player.id = 2
    final_winner = sample_players[2]
    final_winner.id = 3
    initiator_id = 4  # Инициатор перевыбора

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner.id
    mock_game_result.reroll_available = True
    mock_game_result.game_id = game_id
    mock_game_result.year = year
    mock_game_result.day = day

    # Mock database queries
    def exec_side_effect(stmt):
        mock_result = MagicMock()
        if not hasattr(exec_side_effect, 'call_count'):
            exec_side_effect.call_count = 0
        exec_side_effect.call_count += 1

        if exec_side_effect.call_count == 1:
            # First call - get GameResult
            mock_result.first.return_value = mock_game_result
        elif exec_side_effect.call_count == 2:
            # Second call - get old winner
            mock_result.first.return_value = old_winner

        return mock_result

    mock_context.db_session.exec.side_effect = exec_side_effect

    # Mock config
    mock_get_config = mocker.patch('bot.handlers.game.reroll_service.get_config_by_game_id')
    mock_config = MagicMock()
    mock_config.constants.reroll_enabled = True
    mock_config.constants.reroll_price = REROLL_PRICE
    mock_config.constants.coins_per_win = COINS_PER_WIN
    mock_get_config.return_value = mock_config

    # Mock coin operations
    mock_spend = mocker.patch('bot.handlers.game.reroll_service.spend_coins')
    mock_add = mocker.patch('bot.handlers.game.reroll_service.add_coins')
    mock_select = mocker.patch('bot.handlers.game.selection_service.select_winner_with_effects')
    mocker.patch('bot.handlers.game.prediction_service.process_predictions_for_reroll', return_value=[])

    # Mock selection result: защита сработала, перевыбран другой игрок
    mock_selection_result = MagicMock()
    mock_selection_result.winner = final_winner
    mock_selection_result.all_protected = False
    mock_selection_result.had_immunity = True  # Защита сработала!
    mock_selection_result.protected_player = protected_player
    mock_select.return_value = mock_selection_result

    # Execute reroll
    old_winner_result, new_winner_result, selection_result = execute_reroll(
        mock_context.db_session, game_id, year, day, initiator_id, sample_players, current_date
    )

    # Verify results
    assert old_winner_result == old_winner
    assert new_winner_result == final_winner

    # Verify coins were spent from initiator
    mock_spend.assert_called_once_with(
        mock_context.db_session, game_id, initiator_id, REROLL_PRICE, year, "reroll", auto_commit=False
    )

    # Verify coins were added to protected player (immunity reward) and final winner
    assert mock_add.call_count == 2
    mock_add.assert_any_call(
        mock_context.db_session, game_id, protected_player.id, COINS_PER_WIN, year, "immunity_save_reroll", auto_commit=False
    )
    mock_add.assert_any_call(
        mock_context.db_session, game_id, final_winner.id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify GameResult was updated
    assert mock_game_result.original_winner_id == old_winner.id
    assert mock_game_result.winner_id == final_winner.id
    assert mock_game_result.reroll_available is False
    assert mock_game_result.reroll_initiator_id == initiator_id

    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reroll_with_double_chance(mock_update, mock_context, mock_game, sample_players, mocker):
    """Integration test: full scenario with double chance during reroll."""
    from datetime import date
    from bot.handlers.game.reroll_service import execute_reroll

    # Setup
    game_id = 1
    year = 2024
    day = 100
    current_date = date(2024, 4, 10)

    # Игроки: [0] - старый победитель, [1] - победитель с двойным шансом
    old_winner = sample_players[0]
    old_winner.id = 1
    double_chance_winner = sample_players[1]
    double_chance_winner.id = 2
    initiator_id = 3

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner.id
    mock_game_result.reroll_available = True
    mock_game_result.game_id = game_id
    mock_game_result.year = year
    mock_game_result.day = day

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

    mock_context.db_session.exec.side_effect = exec_side_effect

    # Mock config
    mock_get_config = mocker.patch('bot.handlers.game.reroll_service.get_config_by_game_id')
    mock_config = MagicMock()
    mock_config.constants.reroll_enabled = True
    mock_config.constants.reroll_price = REROLL_PRICE
    mock_config.constants.coins_per_win = COINS_PER_WIN
    mock_get_config.return_value = mock_config

    # Mock coin operations
    mock_spend = mocker.patch('bot.handlers.game.reroll_service.spend_coins')
    mock_add = mocker.patch('bot.handlers.game.reroll_service.add_coins')
    mock_select = mocker.patch('bot.handlers.game.selection_service.select_winner_with_effects')
    mocker.patch('bot.handlers.game.prediction_service.process_predictions_for_reroll', return_value=[])

    # Mock selection result: победитель с двойным шансом
    mock_selection_result = MagicMock()
    mock_selection_result.winner = double_chance_winner
    mock_selection_result.all_protected = False
    mock_selection_result.had_immunity = False
    mock_selection_result.had_double_chance = True  # Двойной шанс сработал!
    mock_selection_result.protected_player = None
    mock_select.return_value = mock_selection_result

    # Execute reroll
    old_winner_result, new_winner_result, selection_result = execute_reroll(
        mock_context.db_session, game_id, year, day, initiator_id, sample_players, current_date
    )

    # Verify results
    assert old_winner_result == old_winner
    assert new_winner_result == double_chance_winner

    # Verify coins were spent from initiator
    mock_spend.assert_called_once_with(
        mock_context.db_session, game_id, initiator_id, REROLL_PRICE, year, "reroll", auto_commit=False
    )

    # Verify coins were added only to new winner (no immunity reward)
    assert mock_add.call_count == 1
    mock_add.assert_called_with(
        mock_context.db_session, game_id, double_chance_winner.id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify GameResult was updated
    assert mock_game_result.original_winner_id == old_winner.id
    assert mock_game_result.winner_id == double_chance_winner.id
    assert mock_game_result.reroll_available is False

    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reroll_with_predictions(mock_update, mock_context, mock_game, sample_players, mocker):
    """Integration test: full scenario with predictions during reroll."""
    from datetime import date
    from bot.handlers.game.reroll_service import execute_reroll
    from bot.app.models import Prediction

    # Setup
    game_id = 1
    year = 2024
    day = 100
    current_date = date(2024, 4, 10)

    # Игроки: [0] - старый победитель, [1] - новый победитель
    old_winner = sample_players[0]
    old_winner.id = 1
    new_winner = sample_players[1]
    new_winner.id = 2
    initiator_id = 3
    predictor_id = 4  # Игрок, который сделал предсказание

    # Mock GameResult
    mock_game_result = MagicMock()
    mock_game_result.winner_id = old_winner.id
    mock_game_result.reroll_available = True
    mock_game_result.game_id = game_id
    mock_game_result.year = year
    mock_game_result.day = day

    # Mock prediction - предсказал нового победителя
    mock_prediction = MagicMock(spec=Prediction)
    mock_prediction.user_id = predictor_id
    mock_prediction.game_id = game_id
    mock_prediction.year = year
    mock_prediction.day = day
    mock_prediction.predicted_user_ids = f'[{new_winner.id}]'  # Предсказал нового победителя
    mock_prediction.is_correct = False  # Было неправильным для старого победителя

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

    mock_context.db_session.exec.side_effect = exec_side_effect

    # Mock config
    mock_get_config = mocker.patch('bot.handlers.game.reroll_service.get_config_by_game_id')
    mock_config = MagicMock()
    mock_config.constants.reroll_enabled = True
    mock_config.constants.reroll_price = REROLL_PRICE
    mock_config.constants.coins_per_win = COINS_PER_WIN
    mock_get_config.return_value = mock_config

    # Mock coin operations and predictions
    mock_spend = mocker.patch('bot.handlers.game.reroll_service.spend_coins')
    mock_add = mocker.patch('bot.handlers.game.reroll_service.add_coins')
    mock_select = mocker.patch('bot.handlers.game.selection_service.select_winner_with_effects')
    mock_process_predictions = mocker.patch('bot.handlers.game.prediction_service.process_predictions_for_reroll')

    # Mock selection result
    mock_selection_result = MagicMock()
    mock_selection_result.winner = new_winner
    mock_selection_result.all_protected = False
    mock_selection_result.had_immunity = False
    mock_selection_result.had_double_chance = False
    mock_selection_result.protected_player = None
    mock_select.return_value = mock_selection_result

    # Mock predictions processing - предсказание сбылось при перевыборе
    mock_process_predictions.return_value = [(mock_prediction, True)]

    # Execute reroll
    old_winner_result, new_winner_result, selection_result = execute_reroll(
        mock_context.db_session, game_id, year, day, initiator_id, sample_players, current_date
    )

    # Verify results
    assert old_winner_result == old_winner
    assert new_winner_result == new_winner

    # Verify coins were spent from initiator
    mock_spend.assert_called_once_with(
        mock_context.db_session, game_id, initiator_id, REROLL_PRICE, year, "reroll", auto_commit=False
    )

    # Verify coins were added to new winner
    assert mock_add.call_count == 1
    mock_add.assert_called_with(
        mock_context.db_session, game_id, new_winner.id, COINS_PER_WIN, year, "pidor_win_reroll", auto_commit=False
    )

    # Verify predictions were processed for new winner
    mock_process_predictions.assert_called_once_with(
        mock_context.db_session, game_id, year, day, new_winner.id
    )

    # Verify GameResult was updated
    assert mock_game_result.original_winner_id == old_winner.id
    assert mock_game_result.winner_id == new_winner.id
    assert mock_game_result.reroll_available is False

    # Verify commit was called
    mock_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_give_coins_button_appears_after_pidor_selection(mock_update, mock_context, mock_game, sample_players, mocker):
    """Интеграционный тест: кнопка 'Дайте койнов' появляется после выбора пидора дня."""
    from bot.handlers.game.commands import pidor_cmd
    from bot.handlers.game.text_static import GIVE_COINS_BUTTON_TEXT

    # Mock asyncio.sleep
    mocker.patch('asyncio.sleep', new_callable=AsyncMock)

    # Mock random.choice для выбора победителя
    mock_choice = mocker.patch('bot.handlers.game.commands.random.choice')
    winner = sample_players[0]
    mock_choice.side_effect = [
        winner,  # winner
        "Stage 1",
        "Stage 2",
        "Stage 3",
        "Stage 4: {username}",
    ]

    # Mock datetime
    mock_dt = MagicMock()
    mock_dt.year = 2026
    mock_dt.month = 1
    mock_dt.day = 29
    mock_dt.timetuple.return_value.tm_yday = 29
    mock_dt.date.return_value = MagicMock()
    mocker.patch('bot.handlers.game.commands.current_datetime', return_value=mock_dt)

    # Setup game with players
    mock_game.players = sample_players
    mock_context.game = mock_game
    mock_context.tg_user = sample_players[1]

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
    mock_result_query.one.return_value = MagicMock(winner_id=winner.id)

    mock_context.db_session.query.side_effect = [
        mock_game_query,
        mock_missed_query,
        mock_result_query,
        mock_result_query
    ]

    # Mock send_result_with_reroll_button
    mock_send_result = mocker.patch('bot.handlers.game.commands.send_result_with_reroll_button', new_callable=AsyncMock)

    # Execute
    await pidor_cmd(mock_update, mock_context)

    # Verify send_result_with_reroll_button was called
    assert mock_send_result.called
    call_args = mock_send_result.call_args

    # Проверяем, что функция была вызвана с правильными параметрами
    assert call_args[0][0] == mock_update
    assert call_args[0][1] == mock_context
    # stage4_message содержит имя победителя
    assert winner.full_username() in call_args[0][2]
    assert call_args[0][3] == 2026  # year
    assert call_args[0][4] == 29  # day


@pytest.mark.asyncio
@pytest.mark.integration
async def test_give_coins_regular_player_gets_1_coin(mock_update, mock_context, mock_game, sample_players, mocker):
    """Интеграционный тест: обычный игрок получает 1 койн."""
    from bot.handlers.game.commands import handle_give_coins_callback
    from bot.handlers.game.config import GameConstants

    # Получаем значение по умолчанию из конфигурации
    GIVE_COINS_AMOUNT = GameConstants().give_coins_amount

    # Setup
    winner = sample_players[0]
    regular_player = sample_players[1]

    # Важно: используем те же объекты игроков
    mock_game.players = sample_players
    mock_context.game = mock_game
    mock_context.tg_user = regular_player

    # Mock query для ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query

    # Mock callback query
    query = MagicMock()
    query.from_user.id = regular_player.tg_id
    query.data = f"givecoins_{mock_game.id}_2026_29_{winner.id}"
    query.answer = AsyncMock()
    mock_update.callback_query = query

    # Mock has_claimed_today - еще не получал
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_context.db_session.exec.return_value = mock_result

    # Mock get_balance
    mocker.patch('bot.handlers.game.commands.get_balance', return_value=10)

    # Mock get_config_by_game_id
    mock_config = MagicMock()
    mock_config.constants.give_coins_enabled = True
    mock_config.constants.give_coins_amount = GIVE_COINS_AMOUNT
    mock_config.constants.give_coins_winner_amount = GameConstants().give_coins_winner_amount
    mocker.patch('bot.handlers.game.give_coins_service.get_config_by_game_id', return_value=mock_config)

    # Execute
    await handle_give_coins_callback(mock_update, mock_context)

    # Verify
    assert query.answer.called
    # query.answer вызывается с позиционным аргументом (текст)
    answer_text = query.answer.call_args[0][0]
    assert str(GIVE_COINS_AMOUNT) in answer_text
    assert "10" in answer_text  # balance

    # Verify add was called (GiveCoinsClick)
    assert mock_context.db_session.add.called

    # Verify commit was called
    assert mock_context.db_session.commit.called


@pytest.mark.asyncio
@pytest.mark.integration
async def test_give_coins_winner_gets_2_coins(mock_update, mock_context, mock_game, sample_players, mocker):
    """Интеграционный тест: пидор дня получает 2 койна."""
    from bot.handlers.game.commands import handle_give_coins_callback
    from bot.handlers.game.config import GameConstants

    # Получаем значение по умолчанию из конфигурации
    GIVE_COINS_WINNER_AMOUNT = GameConstants().give_coins_winner_amount

    # Setup
    winner = sample_players[0]

    # Важно: используем те же объекты игроков
    mock_game.players = sample_players
    mock_context.game = mock_game
    mock_context.tg_user = winner

    # Mock query для ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query

    # Mock callback query
    query = MagicMock()
    query.from_user.id = winner.tg_id
    query.data = f"givecoins_{mock_game.id}_2026_29_{winner.id}"
    query.answer = AsyncMock()
    mock_update.callback_query = query

    # Mock has_claimed_today - еще не получал
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_context.db_session.exec.return_value = mock_result

    # Mock get_balance
    mocker.patch('bot.handlers.game.commands.get_balance', return_value=15)

    # Mock get_config_by_game_id
    mock_config = MagicMock()
    mock_config.constants.give_coins_enabled = True
    mock_config.constants.give_coins_amount = GameConstants().give_coins_amount
    mock_config.constants.give_coins_winner_amount = GIVE_COINS_WINNER_AMOUNT
    mocker.patch('bot.handlers.game.give_coins_service.get_config_by_game_id', return_value=mock_config)

    # Execute
    await handle_give_coins_callback(mock_update, mock_context)

    # Verify
    assert query.answer.called
    # query.answer вызывается с позиционным аргументом (текст)
    answer_text = query.answer.call_args[0][0]
    assert str(GIVE_COINS_WINNER_AMOUNT) in answer_text
    assert "15" in answer_text  # balance

    # Verify add was called (GiveCoinsClick)
    assert mock_context.db_session.add.called
    added_click = mock_context.db_session.add.call_args[0][0]
    assert added_click.is_winner is True
    assert added_click.amount == GIVE_COINS_WINNER_AMOUNT

    # Verify commit was called
    assert mock_context.db_session.commit.called


@pytest.mark.asyncio
@pytest.mark.integration
async def test_give_coins_cannot_claim_twice(mock_update, mock_context, mock_game, sample_players, mocker):
    """Интеграционный тест: нельзя получить койны дважды в один день."""
    from bot.handlers.game.commands import handle_give_coins_callback
    from bot.handlers.game.text_static import GIVE_COINS_ALREADY_CLAIMED

    # Setup
    winner = sample_players[0]
    regular_player = sample_players[1]

    # Важно: используем те же объекты игроков
    mock_game.players = sample_players
    mock_context.game = mock_game
    mock_context.tg_user = regular_player

    # Mock query для ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query

    # Mock callback query
    query = MagicMock()
    query.from_user.id = regular_player.tg_id
    query.data = f"givecoins_{mock_game.id}_2026_29_{winner.id}"
    query.answer = AsyncMock()
    mock_update.callback_query = query

    # Mock has_claimed_today - уже получал
    mock_click = MagicMock()
    mock_result = MagicMock()
    mock_result.first.return_value = mock_click
    mock_context.db_session.exec.return_value = mock_result

    # Execute
    await handle_give_coins_callback(mock_update, mock_context)

    # Verify
    assert query.answer.called
    # query.answer вызывается с позиционным аргументом (текст)
    answer_text = query.answer.call_args[0][0]
    assert GIVE_COINS_ALREADY_CLAIMED in answer_text

    # Verify add was NOT called
    assert not mock_context.db_session.add.called

    # Verify commit was NOT called
    assert not mock_context.db_session.commit.called


@pytest.mark.asyncio
@pytest.mark.integration
async def test_give_coins_unregistered_player_error(mock_update, mock_context, mock_game, sample_players, mocker):
    """Интеграционный тест: незарегистрированный игрок не может получить койны."""
    from bot.handlers.game.commands import handle_give_coins_callback
    from bot.handlers.game.text_static import GIVE_COINS_ERROR_NOT_REGISTERED

    # Setup
    winner = sample_players[0]
    unregistered_player = sample_players[1]

    # Игрок не в списке зарегистрированных
    mock_game.players = [winner]
    mock_context.game = mock_game
    mock_context.tg_user = unregistered_player

    # Mock query для ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query

    # Mock callback query
    query = MagicMock()
    query.from_user.id = unregistered_player.tg_id
    query.data = f"givecoins_{mock_game.id}_2026_29_{winner.id}"
    query.answer = AsyncMock()
    mock_update.callback_query = query

    # Execute
    await handle_give_coins_callback(mock_update, mock_context)

    # Verify
    assert query.answer.called
    # query.answer вызывается с позиционным аргументом (текст)
    answer_text = query.answer.call_args[0][0]
    assert GIVE_COINS_ERROR_NOT_REGISTERED in answer_text

    # Verify add was NOT called
    assert not mock_context.db_session.add.called

    # Verify commit was NOT called
    assert not mock_context.db_session.commit.called
