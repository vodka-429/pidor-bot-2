from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from bot.app.models import (
    DoubleChancePurchase, Game, GamePlayerEffect, GameResult, PidorCoinTransaction, TGUser,
)
from bot.handlers.game import selection_service
from bot.handlers.game.commands import pidor_cmd
from bot.handlers.game.config import ChatConfig, GameConstants
from bot.handlers.game.draw_schedule_service import (
    MOSCOW_TZ, as_utc, choose_next_draw_at, format_draw_locked,
)


@pytest.mark.parametrize('hour', [0, 18])
@pytest.mark.parametrize('today,tomorrow', [
    ('2026-10-18', '2026-10-19'),
    ('2026-10-31', '2026-11-01'),
    ('2026-12-31', '2027-01-01'),
    ('2028-02-28', '2028-02-29'),
])
def test_next_day_uses_moscow_calendar_and_inclusive_hours(mocker, hour, today, tomorrow):
    # 00:05 Moscow is still the previous UTC date.
    now = datetime.fromisoformat(today).replace(hour=0, minute=5, tzinfo=MOSCOW_TZ)
    rng = mocker.patch('bot.handlers.game.draw_schedule_service.random.randint', return_value=hour)
    result = choose_next_draw_at(now.astimezone(timezone.utc))
    assert result.tzinfo == timezone.utc
    assert result.astimezone(MOSCOW_TZ) == datetime.fromisoformat(tomorrow).replace(hour=hour, tzinfo=MOSCOW_TZ)
    rng.assert_called_once_with(0, 18)


def test_countdown_rounds_up_to_minute():
    opening = datetime(2026, 10, 18, tzinfo=MOSCOW_TZ)
    text = format_draw_locked(opening, opening - timedelta(seconds=1))
    assert '18.10.2026 с 00:00 МСК' in text
    assert '0 ч 1 мин' in text


@pytest.fixture
def scheduled_game(mocker):
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        players = [TGUser(tg_id=i, first_name=f'Player{i}', username=f'player{i}') for i in (1, 2)]
        game = Game(chat_id=-1003932067905, players=players)
        session.add(game)
        session.commit()
        for player in players:
            session.add(GamePlayerEffect(game_id=game.id, user_id=player.id))
        session.commit()
        config = ChatConfig(chat_id=game.chat_id, constants=GameConstants(
            random_start_enabled=True, changelog_enabled=False,
            achievements_enabled=False, birthday_enabled=False,
            reroll_enabled=False, give_coins_enabled=False,
            game_result_time_delay=0,
        ))
        mocker.patch('bot.handlers.game.commands.get_config', return_value=config)
        mocker.patch('bot.handlers.game.config.get_config', return_value=config)
        mocker.patch('bot.handlers.game.changelog_service.get_config', return_value=config)
        clock = mocker.patch('bot.handlers.game.commands.current_datetime', return_value=datetime(2026, 10, 18, tzinfo=MOSCOW_TZ))
        rng = mocker.patch('bot.handlers.game.draw_schedule_service.random.randint', return_value=14)
        selection = mocker.spy(selection_service, 'select_winner_with_effects')
        chat = SimpleNamespace(id=game.chat_id, send_message=AsyncMock())
        update = SimpleNamespace(effective_chat=chat, message=SimpleNamespace(reply_markdown_v2=AsyncMock()))
        context = SimpleNamespace(db_session=session, tg_user=players[0], game=game, bot=AsyncMock())
        yield SimpleNamespace(
            engine=engine, session=session, game=game, players=players,
            config=config, clock=clock, rng=rng, selection=selection,
            update=update, context=context,
        )
    engine.dispose()


@pytest.mark.asyncio
async def test_first_draw_persists_schedule_and_repeat_shows_it(scheduled_game):
    env = scheduled_game
    await pidor_cmd(env.update, env.context)
    expected = datetime(2026, 10, 19, 14, tzinfo=MOSCOW_TZ)
    assert as_utc(env.game.next_draw_at) == expected.astimezone(timezone.utc)
    result = env.session.exec(select(GameResult)).one()
    assert (result.game_id, result.year, result.day) == (env.game.id, 2026, 291)
    coins = env.session.exec(select(PidorCoinTransaction)).all()
    assert coins
    assert '19.10.2026 с 14:00 МСК' in env.update.effective_chat.send_message.await_args.args[0]
    await pidor_cmd(env.update, env.context)
    env.rng.assert_called_once()
    assert '19\\.10\\.2026 с 14:00 МСК' in env.update.message.reply_markdown_v2.await_args.args[0]
    assert len(env.session.exec(select(PidorCoinTransaction)).all()) == len(coins)
    with Session(env.engine) as restarted:
        assert as_utc(restarted.get(Game, env.game.id).next_draw_at) == expected.astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_locked_draw_does_not_change_game_and_opens_on_boundary(scheduled_game):
    env = scheduled_game
    opening = datetime(2026, 10, 19, 18, tzinfo=MOSCOW_TZ)
    env.game.next_draw_at = opening.astimezone(timezone.utc)
    purchase = DoubleChancePurchase(game_id=env.game.id, buyer_id=env.players[0].id,
                                   target_id=env.players[0].id, year=2026, day=292)
    env.session.add(purchase)
    env.session.commit()
    env.clock.return_value = opening - timedelta(seconds=1)
    for _ in range(2):
        await pidor_cmd(env.update, env.context)
    env.selection.assert_not_called()
    env.rng.assert_not_called()
    assert not env.session.exec(select(GameResult)).all()
    assert not env.session.exec(select(PidorCoinTransaction)).all()
    assert not purchase.is_used
    assert env.update.effective_chat.send_message.await_count == 2
    assert '0 ч 1 мин' in env.update.effective_chat.send_message.await_args.args[0]
    env.clock.return_value = opening
    await pidor_cmd(env.update, env.context)
    assert len(env.session.exec(select(GameResult)).all()) == 1
    env.rng.assert_called_once()


@pytest.mark.asyncio
async def test_missed_day_does_not_delay_current_draw(scheduled_game):
    env = scheduled_game
    env.game.next_draw_at = datetime(2026, 10, 19, 18, tzinfo=MOSCOW_TZ).astimezone(timezone.utc)
    env.session.commit()
    env.clock.return_value = datetime(2026, 10, 20, tzinfo=MOSCOW_TZ)
    await pidor_cmd(env.update, env.context)
    assert env.session.exec(select(GameResult)).one().day == 293
    assert as_utc(env.game.next_draw_at) == datetime(2026, 10, 21, 14, tzinfo=MOSCOW_TZ).astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_disabled_keeps_legacy_behavior(scheduled_game):
    env = scheduled_game
    env.config.constants.random_start_enabled = False
    # Even a retained future schedule must not affect a disabled feature.
    future = datetime(2026, 10, 20, tzinfo=timezone.utc)
    env.game.next_draw_at = future
    env.session.commit()
    await pidor_cmd(env.update, env.context)
    env.rng.assert_not_called()
    assert len(env.session.exec(select(GameResult)).all()) == 1
    assert as_utc(env.game.next_draw_at) == future


@pytest.mark.asyncio
async def test_enabled_works_before_original_activation_date(scheduled_game):
    env = scheduled_game
    env.clock.return_value = datetime(2026, 10, 17, 18, 30, tzinfo=MOSCOW_TZ)
    await pidor_cmd(env.update, env.context)
    result = env.session.exec(select(GameResult)).one()
    assert (result.year, result.day) == (2026, 290)
    assert as_utc(env.game.next_draw_at) == datetime(2026, 10, 18, 14, tzinfo=MOSCOW_TZ).astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_existing_result_without_schedule_only_announces_release(scheduled_game):
    env = scheduled_game
    env.clock.return_value = datetime(2026, 10, 17, 18, 30, tzinfo=MOSCOW_TZ)
    env.config.constants.changelog_enabled = True
    result = GameResult(game_id=env.game.id, winner_id=env.players[0].id, year=2026, day=290)
    env.session.add(result)
    env.session.commit()
    await pidor_cmd(env.update, env.context)
    await pidor_cmd(env.update, env.context)
    env.selection.assert_not_called()
    env.rng.assert_not_called()
    assert env.game.next_draw_at is None
    assert env.session.exec(select(GameResult)).one().id == result.id
    assert not env.session.exec(select(PidorCoinTransaction)).all()
    env.update.effective_chat.send_message.assert_awaited_once()
    assert 'Случайное время' in env.update.effective_chat.send_message.await_args.args[0]
    assert env.update.message.reply_markdown_v2.await_count == 2


@pytest.mark.asyncio
async def test_failed_transaction_rolls_back_result_rewards_and_schedule(scheduled_game, mocker):
    env = scheduled_game
    # Fail the actual commit after the result, rewards and schedule were staged.
    def fail_commit():
        assert env.game.next_draw_at is not None
        raise IntegrityError('commit', {}, RuntimeError('test failure'))
    mocker.patch.object(env.session, 'commit', side_effect=fail_commit)
    with pytest.raises(IntegrityError):
        await pidor_cmd(env.update, env.context)
    env.session.rollback()
    with Session(env.engine) as restarted:
        assert restarted.get(Game, env.game.id).next_draw_at is None
        assert not restarted.exec(select(GameResult)).all()
        assert not restarted.exec(select(PidorCoinTransaction)).all()


@pytest.mark.asyncio
async def test_telegram_failure_keeps_committed_schedule(scheduled_game):
    env = scheduled_game
    # First message is the missed-days notice; second is sent after commit.
    env.update.effective_chat.send_message.side_effect = [None, RuntimeError('Telegram unavailable')]
    with pytest.raises(RuntimeError, match='Telegram unavailable'):
        await pidor_cmd(env.update, env.context)
    assert env.session.exec(select(GameResult)).one()
    await pidor_cmd(env.update, env.context)
    env.rng.assert_called_once()
    assert '14:00' in env.update.message.reply_markdown_v2.await_args.args[0]


@pytest.mark.asyncio
async def test_unsuccessful_draw_does_not_create_schedule(scheduled_game):
    env = scheduled_game
    env.game.players.clear()
    env.session.commit()
    await pidor_cmd(env.update, env.context)
    assert env.game.next_draw_at is None
    env.rng.assert_not_called()


@pytest.mark.asyncio
async def test_all_protected_does_not_create_schedule(scheduled_game):
    env = scheduled_game
    for effect in env.session.exec(select(GamePlayerEffect)).all():
        effect.immunity_year = 2026
        effect.immunity_day = 291
    env.session.commit()
    await pidor_cmd(env.update, env.context)
    assert env.game.next_draw_at is None
    assert not env.session.exec(select(GameResult)).all()
    env.rng.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('now,year,day', [('2027-01-01', 2027, 1), ('2028-03-01', 2028, 61)])
async def test_results_keep_year_and_day_of_year(scheduled_game, now, year, day):
    env = scheduled_game
    env.clock.return_value = datetime.fromisoformat(now).replace(tzinfo=MOSCOW_TZ)
    await pidor_cmd(env.update, env.context)
    result = env.session.exec(select(GameResult)).one()
    assert (result.game_id, result.year, result.day) == (env.game.id, year, day)
    assert as_utc(env.game.next_draw_at).astimezone(MOSCOW_TZ).date() == env.clock.return_value.date() + timedelta(days=1)


@pytest.mark.asyncio
async def test_reroll_does_not_change_next_opening(scheduled_game):
    from bot.handlers.game.coin_service import add_coins
    from bot.handlers.game.reroll_service import execute_reroll

    env = scheduled_game
    await pidor_cmd(env.update, env.context)
    opening = as_utc(env.game.next_draw_at)
    env.config.constants.reroll_enabled = True
    add_coins(env.session, env.game.id, env.players[0].id, 100, 2026, 'test')
    result = env.session.exec(select(GameResult)).one()
    execute_reroll(env.session, env.game.id, result.year, result.day, env.players[0].id,
                   env.players, env.clock.return_value.date())
    assert as_utc(env.game.next_draw_at) == opening
    env.rng.assert_called_once()


@pytest.mark.asyncio
async def test_chats_have_independent_schedules(scheduled_game):
    env = scheduled_game
    await pidor_cmd(env.update, env.context)
    first_game_id = env.game.id
    first_opening = as_utc(env.game.next_draw_at)
    other = Game(chat_id=-1001392307997, players=env.players)
    env.session.add(other)
    env.session.commit()
    env.update.effective_chat.id = other.chat_id
    env.rng.return_value = 0
    await pidor_cmd(env.update, env.context)
    assert as_utc(other.next_draw_at) == datetime(2026, 10, 19, tzinfo=MOSCOW_TZ).astimezone(timezone.utc)
    assert as_utc(env.session.get(Game, first_game_id).next_draw_at) == first_opening


def _reroll_env(env, winner_idx, today_winner_idx, previous_winner_idx=None):
    """Prepare a drawn day with `today_winner_idx` as winner; optionally a win on the previous day."""
    from bot.handlers.game.coin_service import add_coins

    env.config.constants.reroll_enabled = True
    env.config.constants.achievements_enabled = True
    now = env.clock.return_value
    year, day = now.year, now.timetuple().tm_yday
    if previous_winner_idx is not None:
        env.session.add(GameResult(game_id=env.game.id, year=year, day=day - 1,
                                   winner_id=env.players[previous_winner_idx].id))
    env.session.add(GameResult(game_id=env.game.id, year=year, day=day,
                               winner_id=env.players[today_winner_idx].id, reroll_available=True))
    env.session.commit()
    add_coins(env.session, env.game.id, env.players[0].id, 100, year, 'test')
    return year, day


def _force_winner(mocker, player):
    from bot.handlers.game.selection_service import SelectionResult

    return mocker.patch(
        'bot.handlers.game.selection_service.select_winner_with_effects',
        return_value=SelectionResult(
            winner=player, had_immunity=False, had_double_chance=False, all_protected=False),
    )


def _reroll(env, year, day):
    from bot.handlers.game.reroll_service import execute_reroll

    return execute_reroll(env.session, env.game.id, year, day, env.players[0].id,
                          env.players, env.clock.return_value.date())


def _achievements(env, user):
    from bot.app.models import UserAchievement

    return {a.achievement_code for a in env.session.exec(
        select(UserAchievement).where(UserAchievement.user_id == user.id)).all()}


def _ach_transactions(env, user):
    return env.session.exec(select(PidorCoinTransaction).where(
        PidorCoinTransaction.user_id == user.id,
        PidorCoinTransaction.reason.like('achievement_%'))).all()


def test_reroll_awards_first_blood_to_new_winner(scheduled_game, mocker):
    env = scheduled_game
    year, day = _reroll_env(env, 1, today_winner_idx=0)
    _force_winner(mocker, env.players[1])

    old, new, _, awarded = _reroll(env, year, day)

    assert new.id == env.players[1].id
    assert [a.achievement_code for a in awarded] == ['first_blood']
    assert _achievements(env, env.players[1]) == {'first_blood'}
    assert [t.reason for t in _ach_transactions(env, env.players[1])] == ['achievement_first_blood']


def test_reroll_awards_streak_to_yesterdays_winner(scheduled_game, mocker):
    env = scheduled_game
    year, day = _reroll_env(env, 1, today_winner_idx=0, previous_winner_idx=1)
    _force_winner(mocker, env.players[1])

    _, _, _, awarded = _reroll(env, year, day)

    # two wins in the year, so no first blood; streak of two days
    assert [a.achievement_code for a in awarded] == ['streak_2']
    assert _achievements(env, env.players[1]) == {'streak_2'}


def test_reroll_same_player_does_not_duplicate_achievements(scheduled_game, mocker):
    from bot.app.models import UserAchievement
    from bot.handlers.game.achievement_service import check_and_award_achievements

    env = scheduled_game
    year, day = _reroll_env(env, 0, today_winner_idx=0)
    check_and_award_achievements(env.session, env.game.id, env.players[0].id, year, day)
    env.session.commit()
    tx_before = len(_ach_transactions(env, env.players[0]))
    assert tx_before == 1
    _force_winner(mocker, env.players[0])

    _, _, _, awarded = _reroll(env, year, day)

    assert awarded == []
    assert len(env.session.exec(select(UserAchievement)).all()) == 1
    assert len(_ach_transactions(env, env.players[0])) == tx_before


def test_reroll_keeps_old_winner_achievements(scheduled_game, mocker):
    from bot.handlers.game.achievement_service import check_and_award_achievements

    env = scheduled_game
    year, day = _reroll_env(env, 1, today_winner_idx=0)
    check_and_award_achievements(env.session, env.game.id, env.players[0].id, year, day)
    env.session.commit()
    old_before = _achievements(env, env.players[0])
    old_tx = len(_ach_transactions(env, env.players[0]))
    assert old_before == {'first_blood'}
    _force_winner(mocker, env.players[1])

    _reroll(env, year, day)

    assert _achievements(env, env.players[0]) == old_before
    assert len(_ach_transactions(env, env.players[0])) == old_tx


def test_reroll_respects_achievements_disabled(scheduled_game, mocker):
    env = scheduled_game
    year, day = _reroll_env(env, 1, today_winner_idx=0)
    env.config.constants.achievements_enabled = False
    _force_winner(mocker, env.players[1])

    _, _, _, awarded = _reroll(env, year, day)

    assert awarded == []
    assert _achievements(env, env.players[1]) == set()
