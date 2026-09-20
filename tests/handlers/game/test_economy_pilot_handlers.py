import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram.constants import ChatMemberStatus

from bot.handlers.game.economy_pilot_handlers import (
    _apply_title,
    _is_expected_shop_reply,
    _manual_title_required,
    _send_shop_input_prompt,
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
async def test_shop_input_prompt_uses_selective_force_reply():
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=77))
    context = SimpleNamespace(bot=bot)
    user = SimpleNamespace(id=123, mention_html=lambda: '<a href="tg://user?id=123">User</a>')

    message_id = await _send_shop_input_prompt(
        context,
        -1001,
        user,
        "пришлите текст",
        "Введите текст",
    )

    assert message_id == 77
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == -1001
    assert kwargs["reply_markup"].selective is True
    assert kwargs["reply_markup"].input_field_placeholder == "Введите текст"


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
