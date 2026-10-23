"""Растущая цена двойного шанса (issue #119)."""
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from bot.app.models import ChatBank, DoubleChancePurchase, Game, PidorCoinTransaction, TGUser
from bot.handlers.game import commands
from bot.handlers.game.changelog_service import (
    DOUBLE_CHANCE_PRICE_RELEASE_ID, build_double_chance_price_changelog_html,
    send_current_changelog,
)
from bot.handlers.game.coin_service import add_coins, get_balance
from bot.handlers.game.config import ChatConfig, GameConstants
from bot.handlers.game.shop_helpers import (
    create_double_chance_keyboard, create_shop_keyboard, format_shop_help_message,
)
from bot.handlers.game.shop_service import (
    buy_double_chance, calculate_double_chance_price, get_double_chance_counts,
)
from bot.handlers.game.text_static import (
    get_double_chance_messages, get_rules_message, get_shop_menu,
)

TODAY = date(2026, 10, 18)
YEAR = 2026
TOMORROW_DAY = date(2026, 10, 19).timetuple().tm_yday


def make_config(step):
    return ChatConfig(chat_id=-1001, constants=GameConstants(double_chance_price_step=step))


@pytest.fixture
def env(mocker):
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        players = [TGUser(tg_id=i, first_name=f'P{i}', username=f'p{i}') for i in range(1, 6)]
        game = Game(chat_id=-1001, players=players)
        session.add(game)
        session.commit()
        for player in players:
            add_coins(session, game.id, player.id, 100, YEAR, 'seed')
        cfg = {'step': 4}

        def config_for(db, game_id):
            return make_config(cfg['step'])

        mocker.patch('bot.handlers.game.shop_service.get_config_by_game_id', side_effect=config_for)
        mocker.patch('bot.handlers.game.shop_service.calculate_commission_amount', return_value=1)
        yield SimpleNamespace(session=session, game=game, players=players, cfg=cfg)
    engine.dispose()


def bank_balance(env):
    bank = env.session.exec(select(ChatBank).where(ChatBank.game_id == env.game.id)).first()
    return bank.balance if bank else 0


def purchases(env):
    return env.session.exec(select(DoubleChancePurchase)).all()


def buy(env, buyer_idx, target_idx, **kwargs):
    return buy_double_chance(
        env.session, env.game.id, env.players[buyer_idx].id, env.players[target_idx].id,
        YEAR, TODAY, **kwargs,
    )


def test_calculate_price():
    c = GameConstants(double_chance_price=8, double_chance_price_step=4)
    assert [calculate_double_chance_price(c, n) for n in range(3)] == [8, 12, 16]
    assert calculate_double_chance_price(GameConstants(double_chance_price_step=-5), 3) == 8
    assert calculate_double_chance_price(GameConstants(double_chance_price=0), 0) == 1


def test_flat_price_when_step_zero(env):
    env.cfg['step'] = 0
    for buyer in range(3):
        assert buy(env, buyer, 4)[0]
        assert get_balance(env.session, env.game.id, env.players[buyer].id) == 92


def test_price_grows_for_same_target(env):
    for buyer, price in enumerate([8, 12, 16]):
        success, message, _ = buy(env, buyer, 4, expected_price=price)
        assert (success, message) == (True, 'success')
        assert get_balance(env.session, env.game.id, env.players[buyer].id) == 100 - price
    counts = get_double_chance_counts(env.session, env.game.id, YEAR, TOMORROW_DAY)
    assert counts == {env.players[4].id: 3}


def test_other_target_and_other_day_do_not_affect_price(env):
    assert buy(env, 0, 4)[0]
    # другая цель — базовая цена
    assert buy(env, 1, 3, expected_price=8)[0]
    # другой день действия — базовая цена
    env.session.add(DoubleChancePurchase(
        game_id=env.game.id, buyer_id=env.players[2].id, target_id=env.players[2].id,
        year=YEAR, day=TOMORROW_DAY + 5,
    ))
    env.session.commit()
    assert get_double_chance_counts(env.session, env.game.id, YEAR, TOMORROW_DAY) == {
        env.players[4].id: 1, env.players[3].id: 1,
    }


def test_used_purchases_still_count(env):
    assert buy(env, 0, 4)[0]
    for item in purchases(env):
        item.is_used = True
        env.session.add(item)
    env.session.commit()
    assert buy(env, 1, 4, expected_price=8) == (False, 'price_changed:12', 0)


def test_wrong_expected_price_changes_nothing(env):
    assert buy(env, 0, 4)[0]
    before_balance = get_balance(env.session, env.game.id, env.players[1].id)
    before_bank = bank_balance(env)
    before_tx = len(env.session.exec(select(PidorCoinTransaction)).all())
    assert buy(env, 1, 4, expected_price=8) == (False, 'price_changed:12', 0)
    assert get_balance(env.session, env.game.id, env.players[1].id) == before_balance
    assert bank_balance(env) == before_bank
    assert len(purchases(env)) == 1
    assert len(env.session.exec(select(PidorCoinTransaction)).all()) == before_tx


def test_expected_price_none_keeps_old_behavior(env):
    assert buy(env, 0, 4)[0]
    assert buy(env, 1, 4)[0]
    assert get_balance(env.session, env.game.id, env.players[1].id) == 88


def test_already_bought_beats_price_changed(env):
    assert buy(env, 0, 4)[0]
    assert buy(env, 0, 3, expected_price=999) == (False, 'already_bought_today', 0)


def test_insufficient_funds_at_raised_price(env):
    assert buy(env, 0, 4)[0]
    assert buy(env, 1, 4)[0]
    env.session.add(PidorCoinTransaction(
        game_id=env.game.id, user_id=env.players[2].id, amount=-90, year=YEAR, reason='burn',
    ))
    env.session.commit()
    assert get_balance(env.session, env.game.id, env.players[2].id) == 10
    assert buy(env, 2, 4, expected_price=16) == (False, 'insufficient_funds', 0)
    assert len(purchases(env)) == 2


def test_price_counts_across_year_boundary(env):
    last_day = date(2026, 12, 31)
    for buyer in range(2):
        success, _, _ = buy_double_chance(
            env.session, env.game.id, env.players[buyer].id, env.players[4].id, 2026, last_day,
        )
        assert success
    assert get_double_chance_counts(env.session, env.game.id, 2027, 1) == {env.players[4].id: 2}
    assert buy_double_chance(
        env.session, env.game.id, env.players[2].id, env.players[4].id, 2026, last_day, expected_price=8,
    ) == (False, 'price_changed:16', 0)


def test_disabled_feature_checked_first(env, mocker):
    mocker.patch(
        'bot.handlers.game.shop_service.get_config_by_game_id',
        return_value=ChatConfig(chat_id=-1, constants=GameConstants(double_chance_enabled=False)),
    )
    assert buy(env, 0, 4, expected_price=1) == (False, 'feature_disabled', 0)


# ---- клавиатуры ----

def players_with_ids():
    return [TGUser(id=i, tg_id=i, first_name=f'P{i}', username=f'p{i}') for i in (1, 2, 3)]


def test_keyboard_without_prices_is_unchanged():
    for prefix in (None, 'shop_immunity_target', 'shop_toast_select'):
        kb = create_double_chance_keyboard(players_with_ids(), owner_user_id=77, callback_prefix=prefix)
        buttons = [b for row in kb.inline_keyboard for b in row]
        base = prefix or 'shop_double_confirm'
        assert [b.callback_data for b in buttons] == [f'{base}_{i}_77' for i in (1, 2, 3)]
        assert [b.text for b in buttons] == ['P1', 'P2', 'P3']


def test_keyboard_with_prices():
    prices = {1: (0, 8), 2: (2, 16)}
    kb = create_double_chance_keyboard(
        players_with_ids(), owner_user_id=77, double_chance_prices=prices, show_counts=True,
    )
    buttons = [b for row in kb.inline_keyboard for b in row]
    assert [b.text for b in buttons] == ['P1', 'P2 ×2 · 16🪙', 'P3']
    assert buttons[0].callback_data == 'shop_double_confirm_1_77_8'
    assert buttons[1].callback_data == 'shop_double_confirm_2_77_16'
    assert buttons[2].callback_data == 'shop_double_confirm_3_77_0'
    assert all(len(b.callback_data.encode()) <= 64 for b in buttons)


def test_keyboard_with_prices_without_counts_when_step_zero():
    kb = create_double_chance_keyboard(
        players_with_ids(), owner_user_id=77, double_chance_prices={1: (3, 8)}, show_counts=False,
    )
    assert kb.inline_keyboard[0][0].text == 'P1'


def test_shop_menu_button_shows_from_price(mocker):
    mocker.patch('bot.handlers.game.shop_service.get_config', return_value=make_config(4))
    texts = [b.text for row in create_shop_keyboard(1, -1001).inline_keyboard for b in row]
    assert '🎲 Шанс · от 8 🪙' in texts
    mocker.patch('bot.handlers.game.shop_service.get_config', return_value=make_config(0))
    texts = [b.text for row in create_shop_keyboard(1, -1001).inline_keyboard for b in row]
    assert '🎲 Шанс · 8 🪙' in texts


def test_help_message_mentions_growth(mocker):
    mocker.patch('bot.handlers.game.shop_service.get_config', return_value=make_config(4))
    text = format_shop_help_message(-1001)
    assert 'от 8 🪙' in text
    assert '+4 за каждый следующий на того же игрока' in text
    assert 'один день' in text


# ---- тексты ----

def test_texts_with_and_without_step():
    on, off = make_config(4), make_config(0)
    for text in (get_shop_menu(on), get_rules_message(on)):
        assert 'от 8 койнов\\, \\+4 за каждый следующий на того же игрока' in text
        assert 'один день' in text
        assert 'до следующей победы' not in text and 'Действует до победы' not in text
    for text in (get_shop_menu(off), get_rules_message(off)):
        assert 'от 8' not in text and '\\+4' not in text
        assert '8 койнов' in text and 'один день' in text
    msgs = get_double_chance_messages(on)
    assert '12' in msgs['purchase_success_self'].format(price=12, date='d', balance=1, commission=1)
    assert '16' in msgs['error_insufficient_funds'].format(price=16, balance=1)
    assert '12' in msgs['error_price_changed'].format(price=12)


# ---- хендлер подтверждения ----

@pytest.fixture
def handler_env(mocker):
    players = [TGUser(id=i, tg_id=100 + i, first_name=f'P{i}', username=f'p{i}') for i in (1, 2, 3)]
    query = MagicMock()
    query.from_user.id = 101
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = SimpleNamespace(
        callback_query=query, effective_chat=SimpleNamespace(id=-1001),
    )
    context = SimpleNamespace(
        db_session=MagicMock(), game=SimpleNamespace(id=1),
        tg_user=SimpleNamespace(id=1, tg_id=101, full_username=lambda: '@buyer'),
    )
    context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = (
        SimpleNamespace(id=1)
    )
    context.db_session.exec.return_value.all.return_value = []
    context.db_session.query.return_value.filter_by.return_value.one.return_value = players[1]
    mocker.patch('bot.handlers.game.commands.current_datetime',
                 return_value=datetime(2026, 10, 18, 12, 0))
    mocker.patch('bot.handlers.game.commands.get_config', return_value=make_config(4))
    mocker.patch('bot.handlers.game.config.get_config', return_value=make_config(4))
    mocker.patch('bot.handlers.game.commands.get_active_players', return_value=players)
    mocker.patch('bot.handlers.game.commands.get_balance', return_value=50)
    mocker.patch('bot.handlers.game.commands.get_deactivated_player_ids', return_value=set())
    return SimpleNamespace(query=query, update=update, context=context, players=players)


def call_confirm(h, data, mocker, result):
    h.query.data = data
    buy = mocker.patch('bot.handlers.game.shop_service.buy_double_chance', return_value=result)
    return buy


@pytest.mark.asyncio
async def test_confirm_new_callback_passes_price(handler_env, mocker):
    buy = call_confirm(handler_env, 'shop_double_confirm_2_101_12', mocker, (True, 'success', 2))
    await commands.handle_shop_double_confirm_callback(handler_env.update, handler_env.context)
    assert buy.call_args.kwargs['expected_price'] == 12
    text = handler_env.query.edit_message_text.await_args.kwargs['text']
    assert '12 койнов' in text


@pytest.mark.asyncio
async def test_confirm_old_callback_uses_base_price(handler_env, mocker):
    buy = call_confirm(handler_env, 'shop_double_confirm_2_101', mocker, (True, 'success', 2))
    await commands.handle_shop_double_confirm_callback(handler_env.update, handler_env.context)
    assert buy.call_args.kwargs['expected_price'] == 8
    assert '8 койнов' in handler_env.query.edit_message_text.await_args.kwargs['text']


@pytest.mark.asyncio
async def test_confirm_price_changed_alerts_and_refreshes_keyboard(handler_env, mocker):
    call_confirm(handler_env, 'shop_double_confirm_2_101_8', mocker, (False, 'price_changed:12', 0))
    await commands.handle_shop_double_confirm_callback(handler_env.update, handler_env.context)
    query = handler_env.query
    assert query.answer.await_args.args[0] == 'Цена изменилась, теперь 12 🪙'
    assert query.answer.await_args.kwargs['show_alert'] is True
    markup = query.edit_message_text.await_args.kwargs['reply_markup']
    assert markup.inline_keyboard[0][0].callback_data == 'shop_double_confirm_1_101_8'


@pytest.mark.asyncio
async def test_confirm_insufficient_funds_shows_actual_price(handler_env, mocker):
    call_confirm(handler_env, 'shop_double_confirm_2_101_16', mocker, (False, 'insufficient_funds', 0))
    await commands.handle_shop_double_confirm_callback(handler_env.update, handler_env.context)
    assert 'Нужно 16 койнов' in handler_env.query.edit_message_text.await_args.kwargs['text']


@pytest.mark.asyncio
async def test_select_handler_shows_prices(handler_env, mocker):
    handler_env.query.data = 'shop_double_101'
    handler_env.context.db_session.exec.return_value.all.return_value = [2, 2]
    await commands.handle_shop_double_callback(handler_env.update, handler_env.context)
    markup = handler_env.query.edit_message_text.await_args.kwargs['reply_markup']
    buttons = [b for row in markup.inline_keyboard for b in row]
    assert buttons[1].text == 'P2 ×2 · 16🪙'
    assert buttons[1].callback_data == 'shop_double_confirm_2_101_16'
    assert buttons[0].text == 'P1'


# ---- анонс ----

@pytest.mark.asyncio
@pytest.mark.parametrize('step', [0, 4])
async def test_announcement_only_where_step_enabled(step):
    engine = create_engine('sqlite://')
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game = Game(chat_id=-1001)
        session.add(game)
        session.commit()
        chat = SimpleNamespace(id=game.chat_id, send_message=AsyncMock())
        update = SimpleNamespace(effective_chat=chat)
        context = SimpleNamespace(db_session=session, game=game)
        config = ChatConfig(chat_id=game.chat_id, constants=GameConstants(
            changelog_enabled=True, double_chance_price_step=step,
        ))
        import bot.handlers.game.changelog_service as svc
        svc.get_config, original = (lambda chat_id: config), svc.get_config
        try:
            with patch.object(svc, 'current_datetime', return_value=datetime(2026, 10, 25, 12, 0)):
                await send_current_changelog(update, context, True)
        finally:
            svc.get_config = original
        from bot.app.models import ChangelogReceipt
        releases = {r.release_id for r in session.exec(select(ChangelogReceipt)).all()}
        assert (DOUBLE_CHANCE_PRICE_RELEASE_ID in releases) is (step > 0)
    engine.dispose()


def test_announcement_text_has_formula():
    html = build_double_chance_price_changelog_html(GameConstants(double_chance_price_step=4))
    assert '8 🪙' in html and '12 🪙' in html and '16 🪙' in html
    assert 'Имя ×2' in html
