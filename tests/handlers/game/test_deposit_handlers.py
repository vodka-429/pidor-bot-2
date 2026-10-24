"""Tests for deposit Telegram handlers (callbacks, ownership, texts)."""
import re
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers.game.config import ChatConfig, GameConstants
from bot.handlers.game.deposit_handlers import (
    deposit_callback,
    deposit_open_callback,
    deposit_term_callback,
    deposit_withdraw_callback,
    deposit_withdraw_confirm_callback,
    handle_shop_deposit_callback,
    handle_shop_deposit_open_callback,
    handle_shop_deposit_term_callback,
    handle_shop_deposit_withdraw_callback,
    handle_shop_deposit_withdraw_confirm_callback,
)
from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP

BIG_TG_ID = 9_999_999_999_999

DISPATCHER_PATTERNS = {
    "deposit": r'^shop_deposit_\d+$',
    "term": r'^shop_deposit_t_\d+_\d+$',
    "open": r'^shop_deposit_x_\d+_\d+_\d+$',
    "withdraw": r'^shop_deposit_w_\d+$',
    "withdraw_ok": r'^shop_deposit_w_ok_\d+$',
}

# Паттерны соседних кнопок магазина, которые не должны перехватывать вклады
OTHER_PATTERNS = [
    r'^shop_duel_\d+$', r'^shop_duel_t_\d+_\d+$', r'^shop_duel_x_\d+_\d+_\d+$',
    r'^shop_police_\d+$', r'^shop_police_ok_\d+$', r'^shop_bank_\d+$', r'^shop_back_\d+$',
    r'^shop_double_\d+$', r'^shop_double_confirm_\d+_\d+(_\d+)?$',
]


@pytest.mark.unit
def test_callback_data_fits_telegram_limit_and_matches_only_own_pattern():
    data = {
        "deposit": deposit_callback(BIG_TG_ID),
        "term": deposit_term_callback(30, BIG_TG_ID),
        "open": deposit_open_callback(30, 200, BIG_TG_ID),
        "withdraw": deposit_withdraw_callback(BIG_TG_ID),
        "withdraw_ok": deposit_withdraw_confirm_callback(BIG_TG_ID),
    }
    for kind, value in data.items():
        assert len(value.encode("utf-8")) <= 64, value
        matching = [name for name, pattern in DISPATCHER_PATTERNS.items() if re.match(pattern, value)]
        assert matching == [kind], (value, matching)
        assert not any(re.match(pattern, value) for pattern in OTHER_PATTERNS), value


def _game_query(mock_context, game):
    query = MagicMock()
    query.filter_by.return_value = query
    query.one_or_none.return_value = game
    mock_context.db_session.query.return_value = query


def _callback(mock_update, data, from_id=100):
    mock_update.callback_query = MagicMock()
    mock_update.callback_query.data = data
    mock_update.callback_query.from_user.id = from_id
    mock_update.callback_query.answer = AsyncMock()
    mock_update.callback_query.edit_message_text = AsyncMock()
    return mock_update.callback_query


def _config(**overrides):
    values = {"deposit_enabled": True}
    values.update(overrides)
    return ChatConfig(chat_id=987654321, constants=GameConstants(**values))


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize("handler,data", [
    (handle_shop_deposit_callback, "shop_deposit_100"),
    (handle_shop_deposit_term_callback, "shop_deposit_t_7_100"),
    (handle_shop_deposit_open_callback, "shop_deposit_x_7_50_100"),
    (handle_shop_deposit_withdraw_callback, "shop_deposit_w_100"),
    (handle_shop_deposit_withdraw_confirm_callback, "shop_deposit_w_ok_100"),
])
async def test_foreign_shop_is_rejected(handler, data, mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, data, from_id=200)

    with patch("bot.handlers.game.deposit_handlers.open_deposit") as mock_open, \
            patch("bot.handlers.game.deposit_handlers.withdraw_deposit") as mock_withdraw:
        await handler(mock_update, mock_context)

    query.answer.assert_awaited_once_with(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
    query.edit_message_text.assert_not_called()
    mock_open.assert_not_called()
    mock_withdraw.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_term_callback_says_bank_is_empty(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, "shop_deposit_t_7_100")

    with patch("bot.handlers.game.deposit_handlers.get_config", return_value=_config()), \
            patch("bot.handlers.game.deposit_handlers.get_key_rate", return_value=21.0), \
            patch("bot.handlers.game.deposit_handlers.get_open_deposit", return_value=None), \
            patch("bot.handlers.game.deposit_handlers.get_balance", return_value=500), \
            patch(
                "bot.handlers.game.deposit_handlers.get_or_create_chat_bank",
                return_value=SimpleNamespace(balance=0),
            ):
        await handle_shop_deposit_term_callback(mock_update, mock_context)

    query.answer.assert_awaited_once_with("❌ Банк пуст, вклады закрыты", show_alert=True)
    query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_term_callback_shows_only_covered_amounts(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, "shop_deposit_t_7_100")

    with patch("bot.handlers.game.deposit_handlers.get_config", return_value=_config()), \
            patch("bot.handlers.game.deposit_handlers.get_key_rate", return_value=21.0), \
            patch("bot.handlers.game.deposit_handlers.get_open_deposit", return_value=None), \
            patch("bot.handlers.game.deposit_handlers.get_balance", return_value=500), \
            patch(
                "bot.handlers.game.deposit_handlers.get_or_create_chat_bank",
                return_value=SimpleNamespace(balance=3),
            ):
        await handle_shop_deposit_term_callback(mock_update, mock_context)

    keyboard = query.edit_message_text.call_args[1]["reply_markup"]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "shop_deposit_x_7_20_100" in callbacks
    assert "shop_deposit_x_7_76_100" in callbacks
    assert not any(data.startswith("shop_deposit_x_7_100") or data.startswith("shop_deposit_x_7_200")
                   for data in callbacks)
    assert "shop_back_100" in callbacks


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deposit_callback_disabled_without_deposit(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, "shop_deposit_100")

    with patch("bot.handlers.game.deposit_handlers.get_config", return_value=_config(deposit_enabled=False)), \
            patch("bot.handlers.game.deposit_handlers.settle_matured_deposits"), \
            patch("bot.handlers.game.deposit_handlers.get_open_deposit", return_value=None):
        await handle_shop_deposit_callback(mock_update, mock_context)

    query.answer.assert_awaited_once_with("❌ Вклады отключены в этом чате", show_alert=True)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deposit_callback_shows_terms(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, "shop_deposit_100")

    with patch("bot.handlers.game.deposit_handlers.get_config", return_value=_config()), \
            patch("bot.handlers.game.deposit_handlers.get_key_rate", return_value=21.0), \
            patch("bot.handlers.game.deposit_handlers.settle_matured_deposits"), \
            patch("bot.handlers.game.deposit_handlers.get_open_deposit", return_value=None):
        await handle_shop_deposit_callback(mock_update, mock_context)

    text = query.edit_message_text.call_args[0][0]
    keyboard = query.edit_message_text.call_args[1]["reply_markup"]
    assert "<b>21%</b>" in text
    assert [button.callback_data for button in keyboard.inline_keyboard[0]] == [
        "shop_deposit_t_7_100", "shop_deposit_t_14_100", "shop_deposit_t_30_100",
    ]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_deposit_callback_shows_open_deposit_with_withdraw_button(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, "shop_deposit_100")
    deposit = SimpleNamespace(
        amount=100, term_days=7, interest=5,
        opened_date=date(2026, 6, 8), matures_on=date(2026, 6, 15),
    )

    with patch("bot.handlers.game.deposit_handlers.get_config", return_value=_config()), \
            patch("bot.handlers.game.deposit_handlers.settle_matured_deposits"), \
            patch("bot.handlers.game.deposit_handlers.get_open_deposit", return_value=deposit), \
            patch("bot.handlers.game.deposit_handlers.is_deposit_arrested", return_value=False):
        await handle_shop_deposit_callback(mock_update, mock_context)

    text = query.edit_message_text.call_args[0][0]
    keyboard = query.edit_message_text.call_args[1]["reply_markup"]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "<b>100</b>" in text and "<b>+5</b>" in text
    assert "shop_deposit_w_100" in callbacks


@pytest.mark.asyncio
@pytest.mark.unit
async def test_arrested_deposit_has_no_withdraw_button(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, "shop_deposit_100")
    deposit = SimpleNamespace(
        amount=100, term_days=7, interest=5,
        opened_date=date(2026, 6, 8), matures_on=date(2026, 6, 15),
    )

    with patch("bot.handlers.game.deposit_handlers.get_config", return_value=_config()), \
            patch("bot.handlers.game.deposit_handlers.settle_matured_deposits"), \
            patch("bot.handlers.game.deposit_handlers.get_open_deposit", return_value=deposit), \
            patch("bot.handlers.game.deposit_handlers.is_deposit_arrested", return_value=True):
        await handle_shop_deposit_callback(mock_update, mock_context)

    text = query.edit_message_text.call_args[0][0]
    keyboard = query.edit_message_text.call_args[1]["reply_markup"]
    callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "арестован" in text
    assert "shop_deposit_w_100" not in callbacks


@pytest.mark.asyncio
@pytest.mark.unit
async def test_open_callback_announces_deposit(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, "shop_deposit_x_7_100_100")
    deposit = SimpleNamespace(
        amount=100, term_days=7, interest=5, rate_bp=2100,
        matures_on=date(2026, 6, 15),
    )

    with patch(
        "bot.handlers.game.deposit_handlers.open_deposit", return_value=(True, "success", deposit),
    ) as mock_open:
        await handle_shop_deposit_open_callback(mock_update, mock_context)

    assert mock_open.call_args[0][3:5] == (100, 7)
    text = query.edit_message_text.call_args[0][0]
    assert "Вклад открыт" in text and "100 + 5" in text


@pytest.mark.asyncio
@pytest.mark.unit
async def test_open_callback_error_is_alert(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, "shop_deposit_x_7_100_100")

    with patch(
        "bot.handlers.game.deposit_handlers.open_deposit", return_value=(False, "bank_empty", None),
    ):
        await handle_shop_deposit_open_callback(mock_update, mock_context)

    query.answer.assert_awaited_once_with("❌ Банк пуст, вклады закрыты", show_alert=True)
    query.edit_message_text.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_withdraw_confirm_arrested_is_alert(mock_update, mock_context, mock_game):
    _game_query(mock_context, mock_game)
    query = _callback(mock_update, "shop_deposit_w_ok_100")

    with patch(
        "bot.handlers.game.deposit_handlers.withdraw_deposit", return_value=(False, "arrested", None),
    ):
        await handle_shop_deposit_withdraw_confirm_callback(mock_update, mock_context)

    query.answer.assert_awaited_once_with("❌ Вклад арестован до разборки «Раз на раз»", show_alert=True)
    query.edit_message_text.assert_not_called()
