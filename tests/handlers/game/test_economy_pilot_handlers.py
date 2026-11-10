import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from sqlmodel import Session, SQLModel, create_engine

from bot.handlers.game.commands import current_datetime
from bot.handlers.game.economy_pilot_handlers import (
    _apply_title,
    _get_draft,
    _is_expected_shop_reply,
    _manual_title_required,
    _send_shop_input_prompt,
    _save_draft,
    handle_shop_draft_cancel_callback,
    handle_shop_text_input,
)


@pytest.mark.unit
def test_manual_title_is_required_for_owner_and_uneditable_admin():
    owner = SimpleNamespace(status=ChatMemberStatus.OWNER)
    uneditable_admin = SimpleNamespace(
        status=ChatMemberStatus.ADMINISTRATOR,
        can_be_edited=False,
    )
    editable_admin = SimpleNamespace(
        status=ChatMemberStatus.ADMINISTRATOR,
        can_be_edited=True,
    )

    assert _manual_title_required(owner) is True
    assert _manual_title_required(uneditable_admin) is True
    assert _manual_title_required(editable_admin) is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_apply_title_uses_admin_custom_title_for_editable_admin():
    bot = MagicMock()
    bot.set_chat_administrator_custom_title = AsyncMock()
    context = SimpleNamespace(
        bot=bot,
        tg_user=SimpleNamespace(tg_id=123),
    )
    member = SimpleNamespace(
        status=ChatMemberStatus.ADMINISTRATOR,
        custom_title="Старый",
    )

    mode, previous = await _apply_title(context, -1001, member, "Новый")

    assert (mode, previous) == ("admin", "Старый")
    bot.set_chat_administrator_custom_title.assert_awaited_once_with(
        chat_id=-1001,
        user_id=123,
        custom_title="Новый",
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_apply_title_uses_member_tag_only_with_permission():
    bot = MagicMock()
    bot.id = 999
    bot.get_chat_member = AsyncMock(return_value=SimpleNamespace(can_manage_tags=True))
    bot.set_chat_member_tag = AsyncMock()
    context = SimpleNamespace(bot=bot, tg_user=SimpleNamespace(tg_id=123))
    member = SimpleNamespace(status=ChatMemberStatus.MEMBER, tag="Старый")

    mode, previous = await _apply_title(context, -1001, member, "Новый")

    assert (mode, previous) == ("member", "Старый")
    bot.set_chat_member_tag.assert_awaited_once_with(
        chat_id=-1001,
        user_id=123,
        tag="Новый",
    )

    bot.get_chat_member = AsyncMock(return_value=SimpleNamespace(can_manage_tags=False))
    with pytest.raises(PermissionError, match="bot_cannot_manage_tags"):
        await _apply_title(context, -1001, member, "Ещё один")


@pytest.mark.unit
def test_shop_input_requires_reply_to_current_prompt():
    current_reply = SimpleNamespace(message_id=42)
    stale_reply = SimpleNamespace(message_id=41)

    assert _is_expected_shop_reply(
        SimpleNamespace(reply_to_message=current_reply),
        {"prompt_message_id": 42},
    ) is True
    assert _is_expected_shop_reply(
        SimpleNamespace(reply_to_message=stale_reply),
        {"prompt_message_id": 42},
    ) is False
    assert _is_expected_shop_reply(
        SimpleNamespace(reply_to_message=None),
        {"prompt_message_id": 42},
    ) is False


@pytest.mark.unit
def test_legacy_shop_input_draft_without_prompt_id_is_not_consumed():
    assert _is_expected_shop_reply(
        SimpleNamespace(reply_to_message=None),
        {"kind": "telegram_title_input"},
    ) is False


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize("kind", ["phrase", "title"])
async def test_shop_input_prompt_does_not_force_reply_and_has_owner_cancel_button(kind):
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=77))
    context = SimpleNamespace(bot=bot)
    user = SimpleNamespace(id=123, mention_html=lambda: '<a href="tg://user?id=123">User</a>')

    message_id = await _send_shop_input_prompt(
        context,
        -1001,
        user,
        "пришлите текст",
        kind,
    )

    assert message_id == 77
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == -1001
    assert isinstance(kwargs["reply_markup"], InlineKeyboardMarkup)
    assert "force_reply" not in kwargs["reply_markup"].to_dict()
    assert kwargs["reply_markup"].inline_keyboard[0][0].callback_data == f"shop_{kind}_clear_draft_123"
    assert "Ответьте именно на это сообщение" in kwargs["text"]
    assert "5 минут" in kwargs["text"]
    assert "reply_to_message_id" not in kwargs
    assert "reply_parameters" not in kwargs


@pytest.mark.asyncio
@pytest.mark.unit
async def test_title_preview_is_sent_without_replying_to_user_message():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    user = SimpleNamespace(
        id=1,
        tg_id=123,
        full_username=lambda: "User",
    )
    context = SimpleNamespace(bot=bot, tg_user=user)
    message = SimpleNamespace(
        text="test",
        message_id=100,
        reply_to_message=SimpleNamespace(message_id=42),
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(
        update_id=7,
        message=message,
        effective_chat=SimpleNamespace(id=-1001),
    )
    draft = SimpleNamespace(value=json.dumps({
        "kind": "telegram_title_input",
        "prompt_message_id": 42,
        "expires_at": current_datetime().timestamp() + 300,
    }))

    with (
        patch(
            "bot.handlers.game.economy_pilot_handlers._get_draft",
            return_value=draft,
        ),
        patch("bot.handlers.game.economy_pilot_handlers._save_draft") as save_draft,
    ):
        await handle_shop_text_input.__wrapped__(update, context)

    save_draft.assert_called_once_with(
        context,
        -1001,
        {"kind": "telegram_title_confirm", "title": "test"},
    )
    bot.send_message.assert_awaited_once()
    message.reply_text.assert_not_awaited()


def _shop_input_update(reply_id):
    return SimpleNamespace(
        update_id=7,
        message=SimpleNamespace(
            text="Обычное сообщение в чате",
            message_id=100,
            reply_to_message=SimpleNamespace(message_id=reply_id) if reply_id else None,
            reply_text=AsyncMock(),
        ),
        effective_chat=SimpleNamespace(id=-1001),
    )


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["victory_phrase_input", "telegram_title_input"])
@pytest.mark.parametrize("expiry", [None, 999, 1000])
@pytest.mark.parametrize("reply_id", [None, 42])
async def test_expired_and_legacy_input_is_discarded_without_capturing_chat_text(kind, expiry, reply_id):
    payload = {"kind": kind, "prompt_message_id": 42, "position": "start"}
    if expiry is not None:
        payload["expires_at"] = expiry
    context = SimpleNamespace(
        tg_user=SimpleNamespace(id=1, tg_id=123, full_username=lambda **kwargs: "@user"),
        bot=MagicMock(),
    )
    context.bot.send_message = AsyncMock()
    update = _shop_input_update(reply_id)
    update.message.text = "test"
    with patch(
        "bot.handlers.game.economy_pilot_handlers._get_draft",
        return_value=SimpleNamespace(value=json.dumps(payload)),
    ), patch(
        "bot.handlers.game.economy_pilot_handlers.current_datetime"
    ) as clock, patch(
        "bot.handlers.game.economy_pilot_handlers._delete_draft"
    ) as delete, patch(
        "bot.handlers.game.economy_pilot_handlers._save_draft"
    ) as save:
        clock.return_value.timestamp.return_value = 1000
        await handle_shop_text_input.__wrapped__(update, context)

    delete.assert_called_once_with(context, -1001)
    save.assert_not_called()
    context.bot.send_message.assert_not_awaited()
    if reply_id:
        update.message.reply_text.assert_awaited_once()
        assert "истекло" in update.message.reply_text.call_args.args[0]
    else:
        update.message.reply_text.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["victory_phrase_input", "telegram_title_input"])
@pytest.mark.parametrize("reply_id", [None, 41])
async def test_active_input_ignores_regular_messages_and_replies_to_other_prompts(kind, reply_id):
    context = SimpleNamespace(tg_user=SimpleNamespace(tg_id=123), bot=MagicMock())
    context.bot.send_message = AsyncMock()
    update = _shop_input_update(reply_id)
    payload = {
        "kind": kind, "position": "start", "prompt_message_id": 42,
        "expires_at": current_datetime().timestamp() + 300,
    }
    with patch(
        "bot.handlers.game.economy_pilot_handlers._get_draft",
        return_value=SimpleNamespace(value=json.dumps(payload)),
    ), patch(
        "bot.handlers.game.economy_pilot_handlers._save_draft"
    ) as save:
        await handle_shop_text_input.__wrapped__(update, context)

    save.assert_not_called()
    context.bot.send_message.assert_not_awaited()
    update.message.reply_text.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_two_users_have_independent_prompts_and_only_explicit_owner_reply_is_accepted():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        contexts = [SimpleNamespace(
            db_session=session,
            tg_user=SimpleNamespace(id=index, tg_id=tg_id, full_username=lambda **kwargs: "@user"),
            bot=SimpleNamespace(send_message=AsyncMock()),
        ) for index, tg_id in enumerate((123, 456), start=1)]
        first, second = contexts
        with patch("bot.handlers.game.economy_pilot_handlers.current_datetime") as clock:
            clock.return_value.timestamp.return_value = 1000
            for context, prompt_id in zip(contexts, (42, 84)):
                _save_draft(context, -1001, {
                    "kind": "victory_phrase_input", "position": "start",
                    "prompt_message_id": prompt_id,
                })
                payload = json.loads(_get_draft(context, -1001).value)
                assert payload["expires_at"] == 1300
                assert payload["prompt_message_id"] == prompt_id
            assert _get_draft(first, -1002) is None

            # A second user replying to the first user's prompt cannot consume either draft.
            update = _shop_input_update(42)
            await handle_shop_text_input.__wrapped__(update, second)
            second.bot.send_message.assert_not_awaited()
            assert json.loads(_get_draft(first, -1001).value)["kind"] == "victory_phrase_input"
            assert json.loads(_get_draft(second, -1001).value)["kind"] == "victory_phrase_input"

            # The owner explicitly replies; only their own draft advances to a preview.
            await handle_shop_text_input.__wrapped__(update, first)
            payload = json.loads(_get_draft(first, -1001).value)
            assert payload["kind"] == "victory_phrase_confirm"
            assert "expires_at" not in payload
            assert "prompt_message_id" not in payload
            first.bot.send_message.assert_awaited_once()
            assert json.loads(_get_draft(second, -1001).value)["kind"] == "victory_phrase_input"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("sender_id,prompt_id,kind,cancelled", [
    (456, 42, "victory_phrase_input", False),
    (123, 41, "victory_phrase_input", False),
    (123, 42, "telegram_title_input", False),
    (123, 42, None, False),
    (123, 42, "victory_phrase_input", True),
])
async def test_input_cancel_only_closes_current_request_of_its_owner(sender_id, prompt_id, kind, cancelled):
    query = SimpleNamespace(
        data="shop_phrase_clear_draft_123",
        from_user=SimpleNamespace(id=sender_id),
        message=SimpleNamespace(message_id=prompt_id),
        answer=AsyncMock(), edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(callback_query=query, effective_chat=SimpleNamespace(id=-1001))
    context = SimpleNamespace(tg_user=SimpleNamespace(tg_id=123))
    draft = SimpleNamespace(value=json.dumps({"kind": kind, "prompt_message_id": 42}))
    with patch(
        "bot.handlers.game.economy_pilot_handlers._get_draft", return_value=draft
    ) as get_draft, patch(
        "bot.handlers.game.economy_pilot_handlers._delete_draft"
    ) as delete:
        await handle_shop_draft_cancel_callback.__wrapped__(update, context)

    if cancelled:
        delete.assert_called_once_with(context, -1001)
        query.edit_message_text.assert_awaited_once()
    else:
        delete.assert_not_called()
        query.edit_message_text.assert_not_awaited()
    if sender_id != 123:
        get_draft.assert_not_called()
    query.answer.assert_awaited_once()
