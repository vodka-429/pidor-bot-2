from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from bot.app.models import ChangelogReceipt, Game
from bot.handlers.game.changelog_service import (
    CURRENT_RELEASE_ID,
    RANDOM_START_RELEASE_ID,
    build_current_changelog_html,
    send_current_changelog,
)
from bot.handlers.game.config import ChatConfig, GameConstants


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [False, True])
async def test_random_start_release_is_scoped_and_immediate(enabled):
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game = Game(chat_id=-1001)
        session.add(game)
        session.commit()
        session.add(ChangelogReceipt(game_id=game.id, release_id=CURRENT_RELEASE_ID))
        session.commit()
        update = SimpleNamespace(effective_chat=SimpleNamespace(id=game.chat_id, send_message=AsyncMock()))
        context = SimpleNamespace(db_session=session, game=game)
        config = ChatConfig(chat_id=game.chat_id, constants=GameConstants(
            changelog_enabled=True, random_start_enabled=enabled,
        ))
        with patch('bot.handlers.game.changelog_service.get_config', return_value=config):
            assert await send_current_changelog(update, context, True) is enabled
            assert not await send_current_changelog(update, context, True)
            assert await send_current_changelog(update, context, False)
        releases = {receipt.release_id for receipt in session.exec(select(ChangelogReceipt)).all()}
        assert (RANDOM_START_RELEASE_ID in releases) is enabled
        text = update.effective_chat.send_message.await_args.args[0]
        assert ('Случайное время' in text) is enabled
        if enabled:
            assert '00:00 до 18:00 МСК' in text
            assert 'Первый розыгрыш' in text


@pytest.mark.asyncio
async def test_failed_announcement_can_be_retried():
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game = Game(chat_id=-1001)
        session.add(game)
        session.commit()
        chat = SimpleNamespace(id=game.chat_id, send_message=AsyncMock(side_effect=RuntimeError('send failed')))
        update = SimpleNamespace(effective_chat=chat)
        context = SimpleNamespace(db_session=session, game=game)
        config = ChatConfig(chat_id=game.chat_id, constants=GameConstants(
            changelog_enabled=True, random_start_enabled=True,
        ))
        with patch('bot.handlers.game.changelog_service.get_config', return_value=config):
            with pytest.raises(RuntimeError, match='send failed'):
                await send_current_changelog(update, context, True)
            assert not session.exec(select(ChangelogReceipt)).all()
            chat.send_message.side_effect = None
            assert await send_current_changelog(update, context, True)
        assert session.exec(select(ChangelogReceipt)).one().release_id == RANDOM_START_RELEASE_ID


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
            constants=GameConstants(
                changelog_enabled=True,
                coin_rain_enabled=True,
                custom_phrase_enabled=True,
                telegram_title_enabled=True,
            ),
        )

        with patch("bot.handlers.game.changelog_service.get_config", return_value=config):
            assert await send_current_changelog(update, context, mark_as_seen=True) is True
            assert await send_current_changelog(update, context, mark_as_seen=True) is False
            assert await send_current_changelog(update, context, mark_as_seen=False) is True

        receipt = session.exec(select(ChangelogReceipt)).one()
        assert receipt.release_id == CURRENT_RELEASE_ID
        assert chat.send_message.await_count == 2
        sent_html = chat.send_message.await_args.args[0]
        assert "Койновый дождь" in sent_html
        assert "Победная фраза" in sent_html
        assert "Telegram-титулы" in sent_html
        assert "тестовая функция" in sent_html
        assert "вручную" in sent_html


@pytest.mark.unit
def test_changelog_only_mentions_features_enabled_in_chat():
    html = build_current_changelog_html(GameConstants(
        coin_rain_enabled=True,
        custom_phrase_enabled=True,
        telegram_title_enabled=False,
    ))

    assert "Койновый дождь" in html
    assert "Победная фраза" in html
    assert "Telegram-титулы" not in html
