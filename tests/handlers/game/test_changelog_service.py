from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from bot.app.models import ChangelogReceipt, Game
from bot.handlers.game import changelog_service
from bot.handlers.game.changelog_service import (
    CHANGELOG_FOOTER,
    COIN_DUEL_RELEASE_ID,
    CURRENT_RELEASE_ID,
    RANDOM_START_RELEASE_ID,
    RELEASES,
    TELEGRAM_MESSAGE_LIMIT,
    Release,
    build_coin_duel_changelog_html,
    build_current_changelog_html,
    select_releases,
    send_current_changelog,
)
from bot.handlers.game.config import ChatConfig, GameConstants

RELEASE_DATES = {release.id: release.released_on for release in RELEASES}
LATEST = max(RELEASE_DATES.values())


def at(day):
    """Мок current_datetime на заданную дату."""
    return patch(
        'bot.handlers.game.changelog_service.current_datetime',
        return_value=datetime(day.year, day.month, day.day, 12, 0),
    )


def ids(releases):
    return [release.id for release in releases]


def make_env(session, constants):
    game = Game(chat_id=-1001)
    session.add(game)
    session.commit()
    chat = SimpleNamespace(id=game.chat_id, send_message=AsyncMock())
    update = SimpleNamespace(effective_chat=chat)
    context = SimpleNamespace(db_session=session, game=game)
    config = ChatConfig(chat_id=game.chat_id, constants=constants)
    return game, chat, update, context, config


def receipts(session):
    return {r.release_id for r in session.exec(select(ChangelogReceipt)).all()}


def sent_texts(chat):
    return [call.args[0] for call in chat.send_message.await_args_list]


ALL_ON = dict(changelog_enabled=True, random_start_enabled=True, duel_enabled=True)


@pytest.mark.unit
def test_select_releases_filters_by_enabled_and_sorts_fresh_first():
    with at(LATEST):
        assert ids(select_releases(GameConstants(**ALL_ON))) == [
            COIN_DUEL_RELEASE_ID, RANDOM_START_RELEASE_ID, CURRENT_RELEASE_ID,
        ]
        assert ids(select_releases(GameConstants(changelog_enabled=True, random_start_enabled=True))) == [
            RANDOM_START_RELEASE_ID, CURRENT_RELEASE_ID,
        ]
        assert ids(select_releases(GameConstants(changelog_enabled=True, duel_enabled=True))) == [
            COIN_DUEL_RELEASE_ID, CURRENT_RELEASE_ID,
        ]


@pytest.mark.unit
def test_select_releases_window_and_fallback():
    release = lambda rid, day: Release(rid, day, lambda c: True, lambda c: rid)
    today = LATEST
    registry = [
        release('old1', today - timedelta(days=100)),
        release('old2', today - timedelta(days=90)),
        release('old3', today - timedelta(days=80)),
        release('old4', today - timedelta(days=70)),
        release('edge', today - timedelta(days=30)),
        release('fresh', today),
    ]
    constants = GameConstants()
    with at(today), patch.object(changelog_service, 'RELEASES', registry):
        # Свежих 2 (< 3) - последние 3 по дате, а не только свежие.
        assert ids(select_releases(constants)) == ['fresh', 'edge', 'old4']
        registry.append(release('fresh2', today - timedelta(days=1)))
        # Свежих 3 - показываем только их (граница окна включительно).
        assert ids(select_releases(constants)) == ['fresh', 'fresh2', 'edge']
        registry.append(release('fresh3', today - timedelta(days=5)))
        # Свежих больше минимума - показываем все свежие.
        assert ids(select_releases(constants)) == ['fresh', 'fresh2', 'fresh3', 'edge']
    with at(today + timedelta(days=1)), patch.object(changelog_service, 'RELEASES', registry):
        assert 'edge' not in ids(select_releases(constants))


@pytest.mark.asyncio
async def test_pidor_sends_only_unseen_in_one_message_and_marks_each():
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game, chat, update, context, config = make_env(session, GameConstants(**ALL_ON))
        session.add(ChangelogReceipt(game_id=game.id, release_id=CURRENT_RELEASE_ID))
        session.commit()
        with at(LATEST), patch('bot.handlers.game.changelog_service.get_config', return_value=config):
            assert await send_current_changelog(update, context, True) is True
            assert chat.send_message.await_count == 1
            text = sent_texts(chat)[0]
            assert text.index('Раз на раз') < text.index('Случайное время')
            assert 'Что нового в PidorBot' not in text
            assert text.endswith(CHANGELOG_FOOTER)
            assert text.count('/pidornews') == 1
            assert chat.send_message.await_args.kwargs == {'parse_mode': 'HTML'}
            assert receipts(session) == set(RELEASE_DATES)
            # Повторный /pidor ничего не шлёт.
            assert await send_current_changelog(update, context, True) is False
            assert chat.send_message.await_count == 1


@pytest.mark.asyncio
async def test_pidor_sends_new_release_after_previous_were_seen():
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game, chat, update, context, config = make_env(
            session, GameConstants(changelog_enabled=True, random_start_enabled=True),
        )
        with at(LATEST), patch('bot.handlers.game.changelog_service.get_config', return_value=config):
            assert await send_current_changelog(update, context, True)
            assert receipts(session) == {CURRENT_RELEASE_ID, RANDOM_START_RELEASE_ID}
            config.constants.duel_enabled = True
            assert await send_current_changelog(update, context, True)
            text = sent_texts(chat)[-1]
            assert 'Раз на раз' in text
            assert 'Случайное время' not in text
            assert receipts(session) == set(RELEASE_DATES)


@pytest.mark.asyncio
async def test_pidornews_sends_whole_set_without_receipts():
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game, chat, update, context, config = make_env(session, GameConstants(**ALL_ON))
        session.add(ChangelogReceipt(game_id=game.id, release_id=CURRENT_RELEASE_ID))
        session.commit()
        with at(LATEST), patch('bot.handlers.game.changelog_service.get_config', return_value=config):
            assert await send_current_changelog(update, context, False)
            assert await send_current_changelog(update, context, False)
        assert chat.send_message.await_count == 2
        text = sent_texts(chat)[0]
        for marker in ('Раз на раз', 'Случайное время', 'Что нового в PidorBot'):
            assert marker in text
        assert receipts(session) == {CURRENT_RELEASE_ID}


@pytest.mark.asyncio
@pytest.mark.parametrize('mark', [False, True])
async def test_changelog_disabled_sends_nothing(mark):
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        constants = GameConstants(**{**ALL_ON, 'changelog_enabled': False})
        game, chat, update, context, config = make_env(session, constants)
        with at(LATEST), patch('bot.handlers.game.changelog_service.get_config', return_value=config):
            assert await send_current_changelog(update, context, mark) is False
        chat.send_message.assert_not_awaited()
        assert not receipts(session)


@pytest.mark.asyncio
async def test_long_changelog_is_split_on_release_boundaries():
    big = lambda rid: Release(rid, LATEST, lambda c: True, lambda c: rid + 'x' * 3000)
    registry = [big('a'), big('b'), big('c')]
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game, chat, update, context, config = make_env(session, GameConstants(changelog_enabled=True))
        with at(LATEST), patch.object(changelog_service, 'RELEASES', registry), \
                patch('bot.handlers.game.changelog_service.get_config', return_value=config):
            assert await send_current_changelog(update, context, True)
        texts = sent_texts(chat)
        assert len(texts) == 3
        assert all(len(t) <= TELEGRAM_MESSAGE_LIMIT for t in texts)
        assert [t[0] for t in texts] == ['a', 'b', 'c']
        assert texts[-1].endswith(CHANGELOG_FOOTER)
        assert not texts[0].endswith(CHANGELOG_FOOTER)
        assert receipts(session) == {'a', 'b', 'c'}


@pytest.mark.asyncio
async def test_footer_goes_to_own_message_when_it_does_not_fit():
    section = 'a' * (TELEGRAM_MESSAGE_LIMIT - 5)
    registry = [Release('a', LATEST, lambda c: True, lambda c: section)]
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game, chat, update, context, config = make_env(session, GameConstants(changelog_enabled=True))
        with at(LATEST), patch.object(changelog_service, 'RELEASES', registry), \
                patch('bot.handlers.game.changelog_service.get_config', return_value=config):
            assert await send_current_changelog(update, context, True)
        assert sent_texts(chat) == [section, CHANGELOG_FOOTER]
        assert receipts(session) == {'a'}


@pytest.mark.unit
def test_evergreen_texts():
    html = changelog_service.build_random_start_changelog_html()
    assert 'После каждого розыгрыша' in html
    assert '00:00 до 18:00 МСК' in html
    for text in (html, build_coin_duel_changelog_html(GameConstants()), build_current_changelog_html(GameConstants())):
        assert '/pidornews' not in text
        assert 'после обновления' not in text.lower()
        assert '—' not in text


@pytest.mark.unit
def test_coin_duel_changelog_uses_constants():
    html = build_coin_duel_changelog_html(GameConstants(
        duel_max_stake=15, duel_max_leverage=4, police_price=25,
    ))

    assert 'Ставишь до 15' in html
    assert 'в 1-4 раза' in html
    assert 'ментов за 25' in html


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
        with at(LATEST), patch('bot.handlers.game.changelog_service.get_config', return_value=config):
            with pytest.raises(RuntimeError, match='send failed'):
                await send_current_changelog(update, context, True)
            assert not session.exec(select(ChangelogReceipt)).all()
            chat.send_message.side_effect = None
            assert await send_current_changelog(update, context, True)
        assert receipts(session) == {CURRENT_RELEASE_ID, RANDOM_START_RELEASE_ID}


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

        with at(LATEST), patch("bot.handlers.game.changelog_service.get_config", return_value=config):
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
