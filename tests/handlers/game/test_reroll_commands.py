"""Tests for reroll action buttons and callback handling."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handlers.game.config import ChatConfig, GameConstants


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("reroll_enabled", "give_coins_enabled", "expected_callbacks"),
    [
        (True, True, ["reroll_3_2026_254", "givecoins_3_2026_254_29"]),
        (False, True, ["givecoins_3_2026_254_29"]),
        (True, False, ["reroll_3_2026_254"]),
        (False, False, []),
    ],
)
async def test_result_buttons_respect_feature_flags(
    mock_update,
    mock_context,
    mocker,
    reroll_enabled,
    give_coins_enabled,
    expected_callbacks,
):
    from bot.handlers.game.commands import send_result_with_reroll_button

    mock_context.game = MagicMock(id=3)
    game_result = MagicMock(winner_id=29)
    result_query = MagicMock()
    result_query.filter_by.return_value = result_query
    result_query.one.return_value = game_result
    mock_context.db_session.query.return_value = result_query

    result_message = MagicMock(message_id=18362)
    mock_update.effective_chat.send_message = AsyncMock(return_value=result_message)
    config = ChatConfig(
        chat_id=mock_update.effective_chat.id,
        constants=GameConstants(
            reroll_enabled=reroll_enabled,
            give_coins_enabled=give_coins_enabled,
        ),
    )
    mocker.patch("bot.handlers.game.config.get_config", return_value=config)

    scheduled_coroutines = []

    def close_scheduled_coroutine(coroutine):
        scheduled_coroutines.append(coroutine)
        coroutine.close()

    mocker.patch(
        "bot.handlers.game.commands.asyncio.create_task",
        side_effect=close_scheduled_coroutine,
    )

    await send_result_with_reroll_button(
        mock_update, mock_context, "result", 2026, 254
    )

    reply_markup = mock_update.effective_chat.send_message.call_args.kwargs["reply_markup"]
    callbacks = (
        [button.callback_data for button in reply_markup.inline_keyboard[0]]
        if reply_markup
        else []
    )
    assert callbacks == expected_callbacks
    assert len(scheduled_coroutines) == (1 if expected_callbacks else 0)
    assert mock_context.db_session.commit.called is bool(expected_callbacks)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_disabled_reroll_callback_is_handled_without_service_call(
    mock_update, mock_context, mock_game, mocker
):
    from bot.handlers.game.commands import handle_reroll_callback

    mock_context.game = mock_game
    game_query = MagicMock()
    game_query.filter_by.return_value = game_query
    game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = game_query

    query = MagicMock()
    query.from_user.id = mock_context.tg_user.tg_id
    query.data = "reroll_1_2026_254"
    query.answer = AsyncMock()
    mock_update.callback_query = query

    config = ChatConfig(
        chat_id=mock_update.effective_chat.id,
        constants=GameConstants(reroll_enabled=False),
    )
    mocker.patch("bot.handlers.game.config.get_config", return_value=config)
    can_reroll = mocker.patch("bot.handlers.game.reroll_service.can_reroll")
    execute_reroll = mocker.patch("bot.handlers.game.reroll_service.execute_reroll")

    await handle_reroll_callback(mock_update, mock_context)

    query.answer.assert_awaited_once_with(
        "❌ Перевыборы отключены в этом чате",
        show_alert=True,
    )
    can_reroll.assert_not_called()
    execute_reroll.assert_not_called()
