from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from bot.app.models import ChangelogReceipt, Game
from bot.handlers.game.changelog_service import (
    CURRENT_CHANGELOG_HTML,
    CURRENT_RELEASE_ID,
    send_current_changelog,
)
from bot.handlers.game.config import ChatConfig, GameConstants


@pytest.mark.asyncio
@pytest.mark.unit
async def test_changelog_is_sent_once_automatically_and_available_manually():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game = Game(chat_id=-1001)
        session.add(game)
        session.commit()
        session.refresh(game)

        chat = SimpleNamespace(id=-1001, send_message=AsyncMock())
        update = SimpleNamespace(effective_chat=chat)
        context = SimpleNamespace(db_session=session, game=game)
        config = ChatConfig(
            chat_id=-1001,
            constants=GameConstants(changelog_enabled=True),
        )

        with patch("bot.handlers.game.changelog_service.get_config", return_value=config):
            assert await send_current_changelog(update, context, mark_as_seen=True) is True
            assert await send_current_changelog(update, context, mark_as_seen=True) is False
            assert await send_current_changelog(update, context, mark_as_seen=False) is True

        receipt = session.exec(select(ChangelogReceipt)).one()
        assert receipt.release_id == CURRENT_RELEASE_ID
        assert chat.send_message.await_count == 2
        assert "тестовая функция" in CURRENT_CHANGELOG_HTML
        assert "вручную" in CURRENT_CHANGELOG_HTML
