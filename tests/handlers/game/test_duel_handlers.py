"""Tests for «Раз на раз» and police Telegram handlers."""
import re
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.game.duel_handlers import (
    duel_callback,
    duel_stake_callback,
    duel_target_callback,
    handle_shop_duel_callback,
    handle_shop_duel_stake_callback,
    handle_shop_duel_target_callback,
    handle_shop_police_confirm_callback,
    police_callback,
    police_confirm_callback,
)
from bot.handlers.game.config import ChatConfig, GameConstants
from bot.handlers.game.text_static import (
    DUEL_ERROR_ALREADY_IN_DUEL,
    DUEL_ERROR_TARGET_BUSY,
    DUEL_SELECT_TARGET,
    SHOP_ERROR_NOT_YOUR_SHOP,
)

BIG_TG_ID = 9_999_999_999_999
BIG_DB_ID = 2_147_483_647

DISPATCHER_PATTERNS = {
    "duel": r'^shop_duel_\d+$',
    "target": r'^shop_duel_t_\d+_\d+$',
    "stake": r'^shop_duel_x_\d+_\d+_\d+$',
    "police": r'^shop_police_\d+$',
    "police_ok": r'^shop_police_ok_\d+$',
}


@pytest.mark.unit
def test_callback_data_fits_telegram_limit_and_matches_only_own_pattern():
    data = {
        "duel": duel_callback(BIG_TG_ID),
        "target": duel_target_callback(BIG_DB_ID, BIG_TG_ID),
        "stake": duel_stake_callback(BIG_DB_ID, 20, BIG_TG_ID),
        "police": police_callback(BIG_TG_ID),
        "police_ok": police_confirm_callback(BIG_TG_ID),
    }
    for kind, value in data.items():
        assert len(value.encode("utf-8")) <= 64, value
        matching = [name for name, pattern in DISPATCHER_PATTERNS.items() if re.match(pattern, value)]
        assert matching == [kind], (value, matching)


def _game_query(mock_context, game):
    query = MagicMock()
    query.filter_by.return_value = query
    query.one_or_none.return_value = game
    mock_context.db_session.query.return_value = query


def _duel_query(mock_update, data):
    query = MagicMock()
    query.data = data
    query.from_user.id = 100
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    mock_update.callback_query = query
    return query


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("busy_ids", [set(), {2}, {2, 3}])
@pytest.mark.parametrize("same_day,fight_year,fight_day", [
    (False, 2027, 1),
    (True, 2026, 365),
])
async def test_target_menu_marks_players_busy_for_selected_draw(
    busy_ids, same_day, fight_year, fight_day, mock_update, mock_context, mock_game
):
    _game_query(mock_context, mock_game)
    query = _duel_query(mock_update, "shop_duel_100")
    targets = [
        (SimpleNamespace(id=2, first_name="Alice", last_name="Target"), 100),
        (SimpleNamespace(id=3, first_name="Bob", last_name=None), 50),
    ]
    config = ChatConfig(
        chat_id=-1001, constants=GameConstants(duel_enabled=True, duel_same_day=same_day)
    )
    with patch("bot.handlers.game.duel_handlers.get_config", return_value=config), patch(
        "bot.handlers.game.duel_handlers.current_datetime", return_value=datetime(2026, 12, 31, 12)
    ), patch(
        "bot.handlers.game.duel_handlers.get_duel_target_day", return_value=(fight_year, fight_day)
    ) as get_target_day, patch(
        "bot.handlers.game.duel_handlers.get_police_call", return_value=None
    ), patch(
        "bot.handlers.game.duel_handlers.get_challenger_duel_today", return_value=None
    ), patch(
        "bot.handlers.game.duel_handlers.get_player_duel", return_value=None
    ), patch(
        "bot.handlers.game.duel_handlers.get_duel_targets", return_value=targets
    ), patch(
        "bot.handlers.game.duel_handlers.get_duel_player_ids", return_value=busy_ids
    ) as get_busy_players:
        await handle_shop_duel_callback(mock_update, mock_context)

    get_target_day.assert_called_once_with(
        mock_context.db_session, mock_game.id, datetime(2026, 12, 31, 12).date(), same_day
    )
    get_busy_players.assert_called_once_with(
        mock_context.db_session, mock_game.id, fight_year, fight_day
    )
    query.edit_message_text.assert_awaited_once()
    text = query.edit_message_text.await_args.args[0]
    assert text == DUEL_SELECT_TARGET
    rows = query.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard
    assert len(rows) == 2
    for button, (player, balance) in zip(rows[0], targets):
        name = player.first_name + (f" {player.last_name}" if player.last_name else "")
        prefix = "🔒 " if player.id in busy_ids else ""
        assert button.text == f"{prefix}{name} · {balance} 🪙"
        assert button.callback_data == duel_target_callback(player.id, 100)
    assert rows[1][0].callback_data == "shop_back_100"
    query.answer.assert_awaited_once_with()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("handler,data", [
    (handle_shop_duel_callback, "shop_duel_100"),
    (handle_shop_duel_target_callback, "shop_duel_t_5_100"),
])
async def test_busy_challenger_cannot_open_or_continue_duel_menu(
    handler, data, mock_update, mock_context, mock_game
):
    _game_query(mock_context, mock_game)
    query = _duel_query(mock_update, data)
    config = ChatConfig(chat_id=-1001, constants=GameConstants(duel_enabled=True))
    with patch("bot.handlers.game.duel_handlers.get_config", return_value=config), patch(
        "bot.handlers.game.duel_handlers.get_police_call", return_value=None
    ), patch(
        "bot.handlers.game.duel_handlers.get_challenger_duel_today", return_value=None
    ), patch(
        "bot.handlers.game.duel_handlers.get_player_duel", return_value=object()
    ):
        await handler(mock_update, mock_context)

    query.answer.assert_awaited_once_with(DUEL_ERROR_ALREADY_IN_DUEL, show_alert=True)
    query.edit_message_text.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_busy_target_cannot_be_selected_from_old_menu(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _duel_query(mock_update, "shop_duel_t_5_100")
    mock_context.db_session.get.return_value = SimpleNamespace(full_username=lambda: "@target")
    config = ChatConfig(chat_id=-1001, constants=GameConstants(duel_enabled=True))
    with patch("bot.handlers.game.duel_handlers.get_config", return_value=config), patch(
        "bot.handlers.game.duel_handlers.get_player_duel", side_effect=[None, object()]
    ):
        await handle_shop_duel_target_callback(mock_update, mock_context)

    query.answer.assert_awaited_once_with(
        DUEL_ERROR_TARGET_BUSY.format(target="@target"), show_alert=True
    )
    query.edit_message_text.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("reason,expected_text", [
    ("already_in_duel", DUEL_ERROR_ALREADY_IN_DUEL),
    ("target_busy", DUEL_ERROR_TARGET_BUSY.format(target="@target")),
])
async def test_old_stake_button_reports_busy_player_without_announcing_duel(
    reason, expected_text, mock_update, mock_context, mock_game
):
    _game_query(mock_context, mock_game)
    query = _duel_query(mock_update, "shop_duel_x_5_10_100")
    mock_context.db_session.get.return_value = SimpleNamespace(full_username=lambda: "@target")
    with patch(
        "bot.handlers.game.duel_handlers.create_duel", return_value=(False, reason, None)
    ):
        await handle_shop_duel_stake_callback(mock_update, mock_context)

    query.answer.assert_awaited_once_with(expected_text, show_alert=True)
    query.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize("handler,data", [
    (handle_shop_duel_callback, "shop_duel_100"),
    (handle_shop_duel_stake_callback, "shop_duel_x_5_10_100"),
    (handle_shop_police_confirm_callback, "shop_police_ok_100"),
])
async def test_foreign_shop_is_rejected(handler, data, mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.data = data
    mock_update.callback_query.from_user.id = 200
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()

    with patch("bot.handlers.game.duel_handlers.create_duel") as mock_create, \
            patch("bot.handlers.game.duel_handlers.call_police") as mock_police:
        await handler(mock_update, mock_context)

    mock_update.callback_query.answer.assert_awaited_once_with(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
    mock_update.callback_query.edit_message_text.assert_not_called()
    mock_create.assert_not_called()
    mock_police.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_police_cooldown_error_shows_date(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.data = "shop_police_ok_100"
    mock_update.callback_query.from_user.id = 100
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 6, 20, 12, 0)

    with patch(
        "bot.handlers.game.duel_handlers.call_police",
        return_value=(False, "cooldown:2026-06-22", [], None),
    ), patch("bot.handlers.game.shop_helpers.datetime", _FixedDatetime):
        await handle_shop_police_confirm_callback(mock_update, mock_context)

    text = mock_update.callback_query.answer.call_args[0][0]
    assert text == "❌ Ты недавно звонил в полицию. Следующий звонок: 22 июня"
    mock_update.callback_query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_police_success_announces_caller(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.data = "shop_police_ok_100"
    mock_update.callback_query.from_user.id = 100
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()

    with patch(
        "bot.handlers.game.duel_handlers.call_police",
        return_value=(True, "success", [], None),
    ):
        await handle_shop_police_confirm_callback(mock_update, mock_context)

    text = mock_update.callback_query.edit_message_text.call_args[0][0]
    assert text == (
        "🚔 <b>@testuser вызвал ментов!</b>\n"
        "За гаражами патруль - все разборки на завтра отменены, ставки возвращены."
    )
