"""Tests for the totalizator creation conversation."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.app.models import KVItem
from bot.handlers.game.commands import (
    TOTALIZATOR_CREATION_TTL_SECONDS,
    _parse_totalizator_creation_state,
    _serialize_totalizator_creation_state,
    handle_tot_create_callback,
    handle_tot_create_cancel_callback,
    handle_totalizator_creation_text,
)


def _context_with_state(kv_item):
    db_session = MagicMock()
    db_session.query.return_value.filter_by.return_value.one_or_none.return_value = kv_item
    return SimpleNamespace(
        db_session=db_session,
        tg_user=SimpleNamespace(id=7, tg_id=123),
        game=SimpleNamespace(id=11),
    )


def _text_update(text, reply_to_message_id=None):
    reply = (
        SimpleNamespace(message_id=reply_to_message_id)
        if reply_to_message_id is not None else None
    )
    message = SimpleNamespace(
        text=text,
        reply_to_message=reply,
        reply_text=AsyncMock(),
    )
    return SimpleNamespace(
        message=message,
        effective_chat=SimpleNamespace(id=-100, send_message=AsyncMock()),
    )


@pytest.mark.unit
def test_totalizator_creation_state_expires():
    value = _serialize_totalizator_creation_state(42, now=1000)

    assert _parse_totalizator_creation_state(value, now=1001) == 42
    assert _parse_totalizator_creation_state(
        value, now=1000 + TOTALIZATOR_CREATION_TTL_SECONDS
    ) is None


@pytest.mark.unit
@pytest.mark.parametrize('value', ['1', '', '{}', 'null'])
def test_totalizator_creation_state_rejects_legacy_and_invalid_values(value):
    assert _parse_totalizator_creation_state(value, now=1000) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_creation_ignores_text_that_is_not_reply_to_prompt():
    kv_item = KVItem(
        chat_id=-100,
        key='tot_create_123',
        value=_serialize_totalizator_creation_state(42),
    )
    context = _context_with_state(kv_item)
    update = _text_update('А где кнопка перевыбора?')

    await handle_totalizator_creation_text.__wrapped__(update, context)

    update.message.reply_text.assert_not_awaited()
    context.db_session.delete.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_creation_ignores_reply_to_another_message():
    kv_item = KVItem(
        chat_id=-100,
        key='tot_create_123',
        value=_serialize_totalizator_creation_state(42),
    )
    context = _context_with_state(kv_item)
    update = _text_update('15 31.12.2099 Спор', reply_to_message_id=41)

    await handle_totalizator_creation_text.__wrapped__(update, context)

    update.message.reply_text.assert_not_awaited()
    context.db_session.delete.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_creation_silently_removes_legacy_state():
    kv_item = KVItem(chat_id=-100, key='tot_create_123', value='1')
    context = _context_with_state(kv_item)
    update = _text_update('Обычное сообщение')

    await handle_totalizator_creation_text.__wrapped__(update, context)

    update.message.reply_text.assert_not_awaited()
    context.db_session.delete.assert_called_once_with(kv_item)
    context.db_session.commit.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_stake_creates_new_reply_prompt():
    kv_item = KVItem(
        chat_id=-100,
        key='tot_create_123',
        value=_serialize_totalizator_creation_state(42),
    )
    context = _context_with_state(kv_item)
    update = _text_update('нет 31.12.2099 Спор', reply_to_message_id=42)
    update.message.reply_text.return_value = SimpleNamespace(message_id=84)

    await handle_totalizator_creation_text.__wrapped__(update, context)

    update.message.reply_text.assert_awaited_once()
    assert 'Ставка должна быть' in update.message.reply_text.call_args.args[0]
    state = json.loads(kv_item.value)
    assert state['prompt_message_id'] == 84
    context.db_session.add.assert_called_with(kv_item)
    context.db_session.commit.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_valid_reply_creates_totalizator_and_clears_state():
    kv_item = KVItem(
        chat_id=-100,
        key='tot_create_123',
        value=_serialize_totalizator_creation_state(42),
    )
    context = _context_with_state(kv_item)
    update = _text_update('15 31.12.2099 Спор', reply_to_message_id=42)
    update.effective_chat.send_message.return_value = SimpleNamespace(message_id=99)
    totalizator = SimpleNamespace(id=5, option_yes='Да', option_no='Нет', message_id=None)

    with patch(
        'bot.handlers.game.cbr_service.calculate_commission_amount', return_value=2
    ), patch(
        'bot.handlers.game.totalizator_service.create_totalizator', return_value=totalizator
    ) as create_mock, patch(
        'bot.handlers.game.totalizator_service.get_totalizator_bets', return_value=[]
    ), patch(
        'bot.handlers.game.totalizator_service.format_totalizator_message', return_value='created'
    ):
        await handle_totalizator_creation_text.__wrapped__(update, context)

    create_mock.assert_called_once()
    context.db_session.delete.assert_called_once_with(kv_item)
    update.effective_chat.send_message.assert_awaited_once()
    assert totalizator.message_id == 99


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_creation_binds_state_to_prompt_message():
    context = _context_with_state(None)
    query = SimpleNamespace(
        data='tot_create_123',
        from_user=SimpleNamespace(id=123),
        message=SimpleNamespace(message_id=55),
        edit_message_text=AsyncMock(),
        answer=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_chat=SimpleNamespace(id=-100),
    )

    with patch(
        'bot.handlers.game.totalizator_service.get_user_open_totalizators', return_value=[]
    ), patch(
        'bot.handlers.game.totalizator_service.get_open_totalizators', return_value=[]
    ):
        await handle_tot_create_callback.__wrapped__(update, context)

    query.edit_message_text.assert_awaited_once()
    saved_item = context.db_session.add.call_args.args[0]
    assert _parse_totalizator_creation_state(saved_item.value) == 55


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_creation_clears_state():
    kv_item = KVItem(
        chat_id=-100,
        key='tot_create_123',
        value=_serialize_totalizator_creation_state(42),
    )
    context = _context_with_state(kv_item)
    query = SimpleNamespace(
        data='tot_create_cancel_123',
        from_user=SimpleNamespace(id=123),
        edit_message_text=AsyncMock(),
        answer=AsyncMock(),
    )
    update = SimpleNamespace(
        callback_query=query,
        effective_chat=SimpleNamespace(id=-100),
    )

    await handle_tot_create_cancel_callback.__wrapped__(update, context)

    context.db_session.delete.assert_called_once_with(kv_item)
    query.edit_message_text.assert_awaited_once()
    query.answer.assert_awaited_once()
