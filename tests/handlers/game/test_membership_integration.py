"""Integration tests for membership handling in commands."""
import pytest
from unittest.mock import MagicMock, AsyncMock

from bot.app.models import GamePlayer, TGUser
from bot.handlers.game.commands import pidor_cmd, pidoreg_cmd
from bot.handlers.game.text_static import (
    ERROR_NOT_ENOUGH_PLAYERS,
    REGISTRATION_SUCCESS,
    ERROR_ALREADY_REGISTERED,
)


@pytest.fixture
def make_tg_user():
    def _make(user_id, tg_id=None):
        return TGUser(
            id=user_id,
            tg_id=tg_id or (100000 + user_id),
            first_name=f"Player{user_id}",
        )
    return _make


@pytest.fixture
def make_game_player():
    def _make(user_id, game_id=1, is_active=True):
        gp = MagicMock(spec=GamePlayer)
        gp.user_id = user_id
        gp.game_id = game_id
        gp.is_active = is_active
        return gp
    return _make


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pidor_cmd_with_deactivated_players(mock_update, mock_context, mock_game, make_tg_user, mocker):
    """pidor_cmd работает корректно, когда get_active_players возвращает уменьшенный список."""
    all_players = [make_tg_user(1), make_tg_user(2), make_tg_user(3)]
    active_players = [all_players[0], all_players[1]]  # player3 деактивирован

    mock_game.players = all_players
    mock_context.game = mock_game

    # Явно мокируем get_active_players для этого теста
    mocker.patch('bot.handlers.game.commands.get_active_players', return_value=active_players)

    # Настраиваем цепочку query для ensure_game + GameResult
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query

    # Мокируем выбор победителя
    from bot.handlers.game import selection_service
    mock_result = MagicMock()
    mock_result.all_protected = False
    mock_result.had_immunity = False
    mock_result.winner = active_players[0]
    mock_result.winner_id = active_players[0].id
    mock_result.had_double_chance = False
    mocker.patch('bot.handlers.game.selection_service.select_winner_with_effects', return_value=mock_result)
    mocker.patch('bot.handlers.game.prediction_service.process_predictions', return_value=[])
    mocker.patch('bot.handlers.game.prediction_service.format_predictions_summary', return_value='')
    mocker.patch('bot.handlers.game.prediction_service.award_correct_predictions')
    mocker.patch('bot.handlers.game.commands.add_coins')
    mocker.patch('bot.handlers.game.game_effects_service.reset_double_chance', return_value=None)
    mocker.patch('bot.handlers.game.game_effects_service.is_immunity_enabled', return_value=True)

    # game_result query returns None (no existing result)
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = None
    mock_context.db_session.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None

    # Мокируем stage messages
    mocker.patch('bot.handlers.game.commands.random.choice',
                 side_effect=lambda lst: lst[0] if lst else None)

    await pidor_cmd(mock_update, mock_context)

    # Убеждаемся, что команда выполнилась (не отправила ERROR_NOT_ENOUGH_PLAYERS)
    for call in mock_update.effective_chat.send_message.call_args_list:
        assert ERROR_NOT_ENOUGH_PLAYERS not in str(call)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pidor_cmd_not_enough_active_players(mock_update, mock_context, mock_game, make_tg_user, mocker):
    """pidor_cmd отправляет ошибку, если активных игроков < 2."""
    all_players = [make_tg_user(1), make_tg_user(2)]
    mock_game.players = all_players
    mock_context.game = mock_game

    # Только 1 активный игрок после деактивации
    mocker.patch('bot.handlers.game.commands.get_active_players', return_value=[all_players[0]])

    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query

    await pidor_cmd(mock_update, mock_context)

    mock_update.effective_chat.send_message.assert_called_once_with(ERROR_NOT_ENOUGH_PLAYERS)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pidoreg_cmd_reactivates_deactivated_player(mock_update, mock_context, mock_game, make_tg_user, make_game_player):
    """pidoreg_cmd реактивирует деактивированного игрока."""
    player = make_tg_user(1)
    # Игрок уже в списке game.players (деактивирован)
    mock_game.players = [player]
    mock_context.game = mock_game
    mock_context.tg_user = player  # тот же объект

    # GamePlayer запись — деактивирована
    gp = make_game_player(player.id, is_active=False)
    mock_context.db_session.exec.return_value.first.return_value = gp

    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query

    await pidoreg_cmd(mock_update, mock_context)

    # Игрок реактивирован
    assert gp.is_active is True
    mock_update.effective_message.reply_markdown_v2.assert_called_once_with(REGISTRATION_SUCCESS)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_pidoreg_cmd_already_registered_active_player(mock_update, mock_context, mock_game, make_tg_user, make_game_player):
    """pidoreg_cmd возвращает ошибку для активного зарегистрированного игрока."""
    player = make_tg_user(1)
    mock_game.players = [player]
    mock_context.game = mock_game
    mock_context.tg_user = player

    # GamePlayer запись — активна
    gp = make_game_player(player.id, is_active=True)
    mock_context.db_session.exec.return_value.first.return_value = gp

    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query

    await pidoreg_cmd(mock_update, mock_context)

    mock_update.effective_message.reply_markdown_v2.assert_called_once_with(ERROR_ALREADY_REGISTERED)
