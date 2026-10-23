"""Tests for «Раз на раз» and police Telegram handlers."""
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.game.duel_handlers import (
    duel_callback,
    duel_stake_callback,
    duel_target_callback,
    handle_shop_duel_callback,
    handle_shop_duel_stake_callback,
    handle_shop_police_confirm_callback,
    police_callback,
    police_confirm_callback,
)
from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP

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

    with patch(
        "bot.handlers.game.duel_handlers.call_police",
        return_value=(False, "cooldown:2026-06-22", [], None),
    ):
        await handle_shop_police_confirm_callback(mock_update, mock_context)

    text = mock_update.callback_query.answer.call_args[0][0]
    assert text.startswith("❌ Ты недавно звонил в полицию. Следующий звонок: 22 июня")
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
