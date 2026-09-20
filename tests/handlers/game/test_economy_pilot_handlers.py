from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram.constants import ChatMemberStatus

from bot.handlers.game.economy_pilot_handlers import (
    _apply_title,
    _manual_title_required,
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
