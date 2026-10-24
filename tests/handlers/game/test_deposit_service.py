"""Tests for coin deposits: interest math, opening, payout, early withdrawal and duel arrest."""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import func
from sqlmodel import Session, SQLModel, create_engine, select

from bot.app.models import (
    ChatBank,
    CoinDeposit,
    CoinDuel,
    Game,
    GamePlayer,
    PidorCoinTransaction,
    TGUser,
)
from bot.handlers.game.coin_service import (
    get_balance,
    get_leaderboard_by_year,
    get_leaderboard_by_year_with_deposits,
)
from bot.handlers.game.config import ChatConfig, GameConstants
from bot.handlers.game.deposit_service import (
    calc_interest,
    calc_min_amount,
    format_deposit_payouts_block,
    format_rate,
    format_term_percent,
    get_amount_options,
    get_arrested_deposit_ids,
    get_bank_deposit_totals,
    get_open_deposit,
    open_deposit,
    rate_to_bp,
    settle_matured_deposits,
    withdraw_deposit,
)
from bot.handlers.game.duel_service import (
    call_police,
    create_duel,
    format_duel_result_html,
    get_duel_targets,
    resolve_duels_for_day,
)

YEAR = 2026
TODAY = date(2026, 6, 15)          # day 166
TOMORROW = date(2026, 6, 16)       # day 167
TOMORROW_DAY = 167
# Кошельки игроков 0..4 (все транзакции в YEAR)
SEED = [100, 300, 100, 50, 20]
BANK_START = 100


@pytest.fixture
def deposit_session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game = Game(chat_id=-1001)
        session.add(game)
        session.commit()
        session.refresh(game)

        players = []
        for index, amount in enumerate(SEED):
            player = TGUser(
                tg_id=3000 + index,
                username=f"player{index}",
                first_name=f"Player {index}",
            )
            session.add(player)
            session.commit()
            session.refresh(player)
            session.add(GamePlayer(game_id=game.id, user_id=player.id, is_active=True))
            session.add(PidorCoinTransaction(
                game_id=game.id, user_id=player.id, amount=amount, year=YEAR, reason="seed",
            ))
            players.append(player)
        session.add(ChatBank(game_id=game.id, balance=BANK_START))
        session.commit()
        yield session, game, players


@pytest.fixture
def env():
    """Вклады и дуэли включены, ставка ЦБ 21%, комиссия фиксированная (без запросов к ЦБ)."""
    config = ChatConfig(
        chat_id=-1001,
        constants=GameConstants(duel_enabled=True, deposit_enabled=True),
    )
    state = SimpleNamespace(config=config, rate=21.0)
    with patch(
        "bot.handlers.game.deposit_service.get_config_by_game_id", return_value=config,
    ), patch(
        "bot.handlers.game.deposit_service.get_key_rate", side_effect=lambda: state.rate,
    ), patch(
        "bot.handlers.game.duel_service.get_config_by_game_id", return_value=config,
    ), patch(
        "bot.handlers.game.duel_service.calculate_commission_amount",
        side_effect=lambda amount: max(1, amount // 10),
    ), patch(
        "bot.handlers.game.shop_service.calculate_commission_amount",
        side_effect=lambda amount: max(1, amount // 10),
    ):
        yield state


def _bank(session, game):
    return session.exec(select(ChatBank).where(ChatBank.game_id == game.id)).first().balance


def _total_money(session, game):
    """Кошельки + свободный банк + тела и резерв процентов открытых вкладов + банки дуэлей."""
    wallets = session.exec(
        select(func.sum(PidorCoinTransaction.amount)).where(PidorCoinTransaction.game_id == game.id)
    ).first() or 0
    deposits = sum(
        deposit.amount + deposit.interest
        for deposit in session.exec(select(CoinDeposit).where(CoinDeposit.status == "open")).all()
    )
    duels = sum(
        duel.challenger_stake + duel.target_stake - duel.target_deposit_part
        for duel in session.exec(select(CoinDuel).where(CoinDuel.status == "pending")).all()
    )
    return wallets + _bank(session, game) + deposits + duels


def _open(session, game, player, amount, term, day):
    success, reason, deposit = open_deposit(session, game.id, player.id, amount, term, day)
    assert (success, reason) == (True, "success")
    return deposit


def _give(session, game, player, amount):
    session.add(PidorCoinTransaction(
        game_id=game.id, user_id=player.id, amount=amount, year=YEAR, reason="seed",
    ))
    session.commit()


def _txns(session, user, reason):
    return session.exec(select(PidorCoinTransaction).where(
        PidorCoinTransaction.user_id == user.id,
        PidorCoinTransaction.reason == reason,
    )).all()


# --- pure math ---

@pytest.mark.unit
def test_interest_by_term_at_21_percent():
    assert calc_interest(100, 2100, 30) == 21
    assert calc_interest(100, 2100, 14) == 11     # 10.5 -> 11 (половина вверх)
    assert calc_interest(100, 2100, 7) == 5       # 5.25 -> 5


@pytest.mark.unit
def test_interest_by_term_at_16_5_percent():
    assert calc_interest(100, 1650, 30) == 17     # 16.5 -> 17
    assert calc_interest(100, 1650, 14) == 8      # 8.25 -> 8
    assert calc_interest(100, 1650, 7) == 4       # 4.125 -> 4


@pytest.mark.unit
def test_interest_rounds_to_nearest():
    assert calc_interest(9, 2100, 7) == 0         # 0.4725
    assert calc_interest(10, 2100, 7) == 1        # 0.525
    assert calc_interest(50, 1400, 7) == 2        # 1.75
    assert calc_interest(29, 1400, 7) == 1        # 1.015


@pytest.mark.unit
@pytest.mark.parametrize("rate_bp,term,expected", [
    (2100, 7, 10), (2100, 14, 5), (2100, 30, 3),
    (1650, 7, 13), (1650, 14, 7), (1650, 30, 4),
    (1400, 7, 15),
])
def test_min_amount_is_smallest_with_interest_at_least_one(rate_bp, term, expected):
    assert calc_min_amount(rate_bp, term) == expected
    assert calc_interest(expected, rate_bp, term) >= 1
    assert calc_interest(expected - 1, rate_bp, term) == 0


@pytest.mark.unit
def test_min_amount_without_rate():
    assert calc_min_amount(0, 7) is None


@pytest.mark.unit
def test_rate_helpers():
    assert rate_to_bp(21.0) == 2100
    assert rate_to_bp(16.5) == 1650
    assert format_rate(2100) == "21"
    assert format_rate(1650) == "16.5"
    assert format_term_percent(2100, 30) == "21"
    assert format_term_percent(1650, 7) == "4.1"


@pytest.mark.unit
def test_amount_options_cover_only_what_bank_can_pay():
    assert get_amount_options(2100, 7, 200, wallet=1000, bank_free=100) == ([10, 50, 100, 200], "")
    # Банк покрывает проценты не больше 4: интерес(85)=4, интерес(86)=5
    assert get_amount_options(2100, 7, 200, wallet=1000, bank_free=4) == ([10, 50, 85], "")
    assert get_amount_options(2100, 7, 200, wallet=80, bank_free=100) == ([10, 50, 80], "")


@pytest.mark.unit
def test_amount_options_hide_duplicate_percent():
    # 3.5% за 7 дней: 15 -> +1, 50 -> +2, 61 -> +2 (дубль 50), 100 -> +4, 200 -> +7
    assert get_amount_options(1400, 7, 200, wallet=61, bank_free=100) == ([15, 50], "")
    assert get_amount_options(1400, 7, 200, wallet=1000, bank_free=100) == ([15, 50, 100, 200], "")
    # «Всё» с тем же процентом, что у меньшей суммы, тоже скрыто (50 и 60 дают +3)
    assert get_amount_options(2100, 7, 200, wallet=60, bank_free=100) == ([10, 50], "")
    # Минимум показан всегда, даже если кошелёк равен минимуму
    assert get_amount_options(1400, 7, 200, wallet=15, bank_free=100) == ([15], "")


@pytest.mark.unit
def test_amount_options_failures():
    assert get_amount_options(2100, 7, 200, wallet=1000, bank_free=0) == ([], "bank_empty")
    assert get_amount_options(2100, 7, 200, wallet=9, bank_free=100) == ([], "insufficient_funds")
    assert get_amount_options(0, 7, 200, wallet=1000, bank_free=100) == ([], "rate_too_low")
    assert get_amount_options(2100, 7, 9, wallet=1000, bank_free=100) == ([], "rate_too_low")


# --- open ---

@pytest.mark.unit
def test_open_moves_body_and_reserves_interest(deposit_session, env):
    session, game, players = deposit_session
    before = _total_money(session, game)

    deposit = _open(session, game, players[0], 100, 7, TODAY)

    assert (deposit.amount, deposit.interest, deposit.rate_bp) == (100, 5, 2100)
    assert deposit.matures_on == TODAY + timedelta(days=7)
    assert deposit.status == "open"
    assert get_balance(session, game.id, players[0].id) == 0
    assert _bank(session, game) == BANK_START - 5
    open_txn = _txns(session, players[0], "deposit_open")[0]
    assert (open_txn.amount, open_txn.year) == (-100, YEAR)
    assert get_bank_deposit_totals(session, game.id) == (100, 5)
    assert _total_money(session, game) == before


@pytest.mark.unit
def test_open_rejections_change_nothing(deposit_session, env):
    session, game, players = deposit_session
    before = _total_money(session, game)

    assert open_deposit(session, game.id, players[1].id, 201, 30, TODAY)[1] == "invalid_amount"   # потолок
    assert open_deposit(session, game.id, players[0].id, 9, 7, TODAY)[1] == "invalid_amount"      # процент 0
    assert open_deposit(session, game.id, players[0].id, 50, 10, TODAY)[1] == "invalid_term"
    assert open_deposit(session, game.id, players[4].id, 50, 7, TODAY)[1] == "insufficient_funds"  # на руках 20
    env.rate = 0.0
    assert open_deposit(session, game.id, players[0].id, 50, 7, TODAY)[1] == "invalid_amount"
    env.rate = 21.0

    assert session.exec(select(CoinDeposit)).all() == []
    assert _total_money(session, game) == before
    assert _bank(session, game) == BANK_START


@pytest.mark.unit
def test_open_second_deposit_rejected(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[1], 50, 7, TODAY)
    assert open_deposit(session, game.id, players[1].id, 50, 7, TODAY)[1] == "already_open"
    assert len(session.exec(select(CoinDeposit)).all()) == 1


@pytest.mark.unit
def test_open_rejected_when_bank_cannot_cover_interest(deposit_session, env):
    session, game, players = deposit_session
    bank = session.exec(select(ChatBank)).first()
    bank.balance = 4
    session.add(bank)
    session.commit()

    assert open_deposit(session, game.id, players[0].id, 100, 7, TODAY)[1] == "bank_empty"   # нужно 5
    success, _, _ = open_deposit(session, game.id, players[0].id, 80, 7, TODAY)              # нужно 4
    assert success is True
    assert _bank(session, game) == 0


@pytest.mark.unit
def test_open_requires_flag_and_active_player(deposit_session, env):
    session, game, players = deposit_session
    env.config.constants.deposit_enabled = False
    assert open_deposit(session, game.id, players[0].id, 50, 7, TODAY)[1] == "feature_disabled"
    env.config.constants.deposit_enabled = True

    link = session.get(GamePlayer, (game.id, players[0].id))
    link.is_active = False
    session.add(link)
    session.commit()
    assert open_deposit(session, game.id, players[0].id, 50, 7, TODAY)[1] == "not_registered"


# --- payout ---

@pytest.mark.unit
def test_payout_only_at_maturity_and_once(deposit_session, env):
    session, game, players = deposit_session
    before = _total_money(session, game)
    deposit = _open(session, game, players[0], 100, 7, TODAY)

    assert settle_matured_deposits(session, game.id, TODAY + timedelta(days=6)) == []
    assert get_balance(session, game.id, players[0].id) == 0

    paid = settle_matured_deposits(session, game.id, TODAY + timedelta(days=7))
    session.commit()
    assert [d.id for d in paid] == [deposit.id]
    assert get_balance(session, game.id, players[0].id) == 105
    assert deposit.status == "paid" and deposit.paid_interest == 5
    assert _total_money(session, game) == before

    # Повторные вызовы и клики ничего не начисляют
    assert settle_matured_deposits(session, game.id, TODAY + timedelta(days=7)) == []
    assert settle_matured_deposits(session, game.id, TODAY + timedelta(days=30)) == []
    assert get_balance(session, game.id, players[0].id) == 105
    assert len(_txns(session, players[0], "deposit_return")) == 1
    assert len(_txns(session, players[0], "deposit_interest")) == 1


@pytest.mark.unit
def test_payout_later_than_maturity(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[0], 100, 14, TODAY)
    assert len(settle_matured_deposits(session, game.id, TODAY + timedelta(days=40))) == 1
    assert get_balance(session, game.id, players[0].id) == 111


@pytest.mark.unit
def test_rate_is_fixed_at_opening(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[0], 100, 30, TODAY)       # 21 койн
    env.rate = 5.0
    settle_matured_deposits(session, game.id, TODAY + timedelta(days=30))
    assert get_balance(session, game.id, players[0].id) == 121


@pytest.mark.unit
def test_payout_transactions_use_payout_year(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[0], 100, 7, date(2026, 12, 28))
    settle_matured_deposits(session, game.id, date(2027, 1, 4))
    session.commit()

    assert _txns(session, players[0], "deposit_open")[0].year == 2026
    assert _txns(session, players[0], "deposit_return")[0].year == 2027
    assert _txns(session, players[0], "deposit_interest")[0].year == 2027
    assert get_balance(session, game.id, players[0].id) == 105


@pytest.mark.unit
def test_payout_works_with_flag_off_and_for_inactive_player(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[0], 100, 7, TODAY)
    env.config.constants.deposit_enabled = False
    link = session.get(GamePlayer, (game.id, players[0].id))
    link.is_active = False
    session.add(link)
    session.commit()

    paid = settle_matured_deposits(session, game.id, TODAY + timedelta(days=7))
    assert len(paid) == 1
    assert get_balance(session, game.id, players[0].id) == 105


@pytest.mark.unit
def test_payout_block_text(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[0], 100, 7, TODAY)
    paid = settle_matured_deposits(session, game.id, TODAY + timedelta(days=7))

    block = format_deposit_payouts_block(session, paid)

    assert block == "💼 <b>Вклады созрели:</b>\nplayer0 забирает 100 🪙 и 5 🪙 процентов"
    assert format_deposit_payouts_block(session, []) == ""


# --- early withdrawal ---

@pytest.mark.unit
def test_early_withdraw_returns_body_and_interest_goes_to_bank(deposit_session, env):
    session, game, players = deposit_session
    before = _total_money(session, game)
    deposit = _open(session, game, players[0], 100, 7, TODAY)

    success, reason, _ = withdraw_deposit(session, game.id, players[0].id, TODAY + timedelta(days=1))

    assert (success, reason) == (True, "success")
    assert deposit.status == "withdrawn"
    assert get_balance(session, game.id, players[0].id) == 100
    assert _bank(session, game) == BANK_START
    assert _total_money(session, game) == before
    # Повторный клик ничего не даёт, срок потом тоже
    assert withdraw_deposit(session, game.id, players[0].id, TODAY + timedelta(days=1))[1] == "no_deposit"
    assert settle_matured_deposits(session, game.id, TODAY + timedelta(days=9)) == []
    assert get_balance(session, game.id, players[0].id) == 100


@pytest.mark.unit
def test_withdraw_works_with_flag_off(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[0], 100, 7, TODAY)
    env.config.constants.deposit_enabled = False
    assert withdraw_deposit(session, game.id, players[0].id, TODAY)[0] is True


@pytest.mark.unit
def test_withdraw_after_maturity_pays_interest_once(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[0], 100, 7, TODAY)

    success, reason, deposit = withdraw_deposit(session, game.id, players[0].id, TODAY + timedelta(days=7))

    assert (success, reason) == (True, "matured")
    assert deposit.status == "paid"
    assert get_balance(session, game.id, players[0].id) == 105
    assert withdraw_deposit(session, game.id, players[0].id, TODAY + timedelta(days=7))[1] == "no_deposit"


# --- duels: wealth and arrest ---

def _open_target_deposit(session, game, players):
    """Игрок 2: весь кошелёк (100) на вкладе, срок выходит в TODAY."""
    return _open(session, game, players[2], 100, 7, date(2026, 6, 8))


@pytest.mark.unit
def test_deposit_counts_as_wealth_for_targets_and_leverage(deposit_session, env):
    session, game, players = deposit_session
    deposit = _open_target_deposit(session, game, players)
    assert get_balance(session, game.id, players[2].id) == 0

    targets = dict((player.id, wealth) for player, wealth in get_duel_targets(
        session, game.id, players[3].id, players,
    ))
    assert targets[players[2].id] == 100

    # Богатство 100 против 50 у вызывающего: плечо x2, ставка 10 против 20
    success, reason, duel = create_duel(session, game.id, players[3].id, players[2].id, 10, TODAY)
    assert (success, reason) == (True, "success")
    assert (duel.challenger_stake, duel.target_stake) == (10, 20)
    assert duel.target_deposit_id == deposit.id and duel.target_deposit_part == 20


@pytest.mark.unit
def test_challenger_stake_only_from_wallet(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[1], 200, 7, TODAY)         # богатство 100 + 200, кошелёк 100
    _open(session, game, players[0], 100, 7, TODAY)         # кошелёк 0
    assert create_duel(session, game.id, players[0].id, players[1].id, 5, TODAY)[1] == "insufficient_funds"


@pytest.mark.unit
def test_arrest_then_target_loses_deposit_is_collected(deposit_session, env):
    session, game, players = deposit_session
    deposit = _open_target_deposit(session, game, players)
    before = _total_money(session, game)
    _, _, duel = create_duel(session, game.id, players[3].id, players[2].id, 10, TODAY)
    assert get_balance(session, game.id, players[2].id) == 0      # деньги не двигались
    assert get_balance(session, game.id, players[3].id) == 40
    assert _total_money(session, game) == before

    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=[5, 0]):
        results = resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR)
    session.commit()

    assert results[0].winner_id == players[3].id
    assert deposit.status == "collected"
    # Банк дуэли: 10 + 20 (недостача с вклада) = 30, комиссия 3
    assert results[0].commission == 3
    assert get_balance(session, game.id, players[3].id) == 40 + 27
    assert get_balance(session, game.id, players[2].id) == 80     # тело 100 - недостача 20
    assert _bank(session, game) == BANK_START - 5 + 5 + 3          # проценты вернулись + комиссия
    assert _total_money(session, game) == before
    assert get_open_deposit(session, game.id, players[2].id) is None
    assert settle_matured_deposits(session, game.id, TOMORROW) == []

    text = format_duel_result_html(results[0], players[3], players[2])
    assert "вклад закрыт досрочно" in text and "20 🪙" in text
    assert "уходит с 30 💰" in text


@pytest.mark.unit
def test_arrest_then_target_wins_deposit_intact(deposit_session, env):
    session, game, players = deposit_session
    deposit = _open_target_deposit(session, game, players)
    before = _total_money(session, game)
    _, _, duel = create_duel(session, game.id, players[3].id, players[2].id, 10, TODAY)

    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=[0, 5]):
        results = resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR)
    session.commit()

    assert results[0].winner_id == players[2].id
    assert deposit.status == "open" and deposit.amount == 100
    # В банк дуэли вошла только ставка вызывающего: 10, комиссия 1, выигрыш 9
    assert results[0].commission == 1
    assert get_balance(session, game.id, players[2].id) == 9
    assert get_balance(session, game.id, players[3].id) == 40
    assert _total_money(session, game) == before
    assert deposit.id not in get_arrested_deposit_ids(session, game.id, TOMORROW)
    assert "уходит с 10 💰" in format_duel_result_html(results[0], players[3], players[2])

    # Арест снят: срок давно вышел, выплата проходит один раз
    assert len(settle_matured_deposits(session, game.id, TOMORROW)) == 1
    assert get_balance(session, game.id, players[2].id) == 9 + 100 + 5
    assert settle_matured_deposits(session, game.id, TOMORROW) == []


@pytest.mark.unit
def test_arrested_deposit_cannot_be_withdrawn_or_paid(deposit_session, env):
    session, game, players = deposit_session
    deposit = _open_target_deposit(session, game, players)
    create_duel(session, game.id, players[3].id, players[2].id, 10, TODAY)

    assert settle_matured_deposits(session, game.id, TODAY) == []     # срок вышел, но вклад арестован
    assert deposit.status == "open"
    assert withdraw_deposit(session, game.id, players[2].id, TODAY)[1] == "arrested"
    assert get_balance(session, game.id, players[2].id) == 0


@pytest.mark.unit
def test_arrest_lifts_when_fight_day_passed_without_draw(deposit_session, env):
    session, game, players = deposit_session
    deposit = _open_target_deposit(session, game, players)
    create_duel(session, game.id, players[3].id, players[2].id, 10, TODAY)

    assert deposit.id in get_arrested_deposit_ids(session, game.id, TOMORROW)
    # День разборки прошёл без розыгрыша: ставки сгорают по общему правилу, арест снимается
    assert get_arrested_deposit_ids(session, game.id, date(2026, 6, 17)) == set()
    assert withdraw_deposit(session, game.id, players[2].id, date(2026, 6, 17))[0] is True


@pytest.mark.unit
def test_second_duel_cannot_arrest_same_deposit(deposit_session, env):
    session, game, players = deposit_session
    _open_target_deposit(session, game, players)
    create_duel(session, game.id, players[3].id, players[2].id, 10, TODAY)
    before = _total_money(session, game)

    # Другая разборка (завтрашний вызов на послезавтра): кошелёк пуст, вклад уже арестован
    result = create_duel(session, game.id, players[4].id, players[2].id, 5, TOMORROW)

    assert result[:2] == (False, "insufficient_funds")
    assert _total_money(session, game) == before


@pytest.mark.unit
def test_police_refunds_wallet_part_only_and_lifts_arrest(deposit_session, env):
    session, game, players = deposit_session
    deposit = _open_target_deposit(session, game, players)
    _give(session, game, players[2], 30)                       # кошелёк 30 + вклад 100
    before = _total_money(session, game)
    # Богатство 130 против 50: плечо x2.6, ставка 20 -> 52: кошелёк 30 + вклад 22
    _, _, duel = create_duel(session, game.id, players[3].id, players[2].id, 20, TODAY)
    assert (duel.target_stake, duel.target_deposit_part) == (52, 22)
    assert get_balance(session, game.id, players[2].id) == 0

    success, reason, refunded, _ = call_police(session, game.id, players[1].id, TODAY)

    assert (success, reason) == (True, "success")
    assert refunded[0].status == "cancelled"
    assert get_balance(session, game.id, players[2].id) == 30      # вернули только списанное
    assert get_balance(session, game.id, players[3].id) == 50
    assert deposit.status == "open" and deposit.amount == 100
    assert deposit.id not in get_arrested_deposit_ids(session, game.id, TODAY)
    # Цена вызова 30: 3 ушло в банк, 27 сгорело
    assert _total_money(session, game) == before - 27


@pytest.mark.unit
def test_mixed_target_loses_collects_shortfall_only(deposit_session, env):
    session, game, players = deposit_session
    deposit = _open_target_deposit(session, game, players)
    _give(session, game, players[2], 30)
    before = _total_money(session, game)
    create_duel(session, game.id, players[3].id, players[2].id, 20, TODAY)

    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=[5, 0]):
        results = resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR)
    session.commit()

    # Банк дуэли: 20 + 30 (кошелёк) + 22 (вклад) = 72, комиссия 7
    assert results[0].commission == 7
    assert deposit.status == "collected"
    assert get_balance(session, game.id, players[3].id) == 30 + 65
    assert get_balance(session, game.id, players[2].id) == 78      # 100 - 22 вернулось с вклада
    assert _total_money(session, game) == before


@pytest.mark.unit
def test_deposit_without_shortfall_is_not_arrested(deposit_session, env):
    session, game, players = deposit_session
    _open_target_deposit(session, game, players)
    _give(session, game, players[2], 60)                       # кошелёк 60 покрывает ставку 30
    _, _, duel = create_duel(session, game.id, players[3].id, players[2].id, 10, TODAY)

    assert duel.target_deposit_id is None and duel.target_deposit_part == 0
    assert get_arrested_deposit_ids(session, game.id, TODAY) == set()


# --- leaderboard with deposits ---

@pytest.mark.unit
def test_leaderboard_counts_open_deposits(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[3], 50, 7, TODAY)             # годовая сумма игрока 3 стала 0

    plain = dict((user.id, coins) for user, coins in get_leaderboard_by_year(session, game.id, YEAR))
    with_deposits = get_leaderboard_by_year_with_deposits(session, game.id, YEAR)

    assert plain[players[3].id] == 0
    assert dict((user.id, coins) for user, coins in with_deposits)[players[3].id] == 50
    assert [coins for _, coins in with_deposits] == sorted([coins for _, coins in with_deposits], reverse=True)


@pytest.mark.unit
def test_leaderboard_includes_player_with_only_previous_year_coins(deposit_session, env):
    session, game, players = deposit_session
    saver = TGUser(tg_id=3999, username="saver", first_name="Saver")
    session.add(saver)
    session.commit()
    session.refresh(saver)
    session.add(GamePlayer(game_id=game.id, user_id=saver.id, is_active=True))
    session.add(PidorCoinTransaction(
        game_id=game.id, user_id=saver.id, amount=500, year=YEAR - 1, reason="seed",
    ))
    session.commit()
    _open(session, game, saver, 200, 7, date(2025, 12, 20))   # открыт в прошлом году

    plain = [user.id for user, _ in get_leaderboard_by_year(session, game.id, YEAR)]
    board = dict((user.id, coins) for user, coins in get_leaderboard_by_year_with_deposits(session, game.id, YEAR))

    assert saver.id not in plain
    assert board[saver.id] == 200


@pytest.mark.unit
def test_leaderboard_without_deposits_is_unchanged(deposit_session, env):
    session, game, players = deposit_session
    assert get_leaderboard_by_year_with_deposits(session, game.id, YEAR, limit=3) == \
        get_leaderboard_by_year(session, game.id, YEAR, limit=3)


@pytest.mark.unit
def test_leaderboard_limit_applies_after_adding_deposits(deposit_session, env):
    session, game, players = deposit_session
    _open(session, game, players[3], 50, 7, TODAY)
    board = get_leaderboard_by_year_with_deposits(session, game.id, YEAR, limit=2)
    assert len(board) == 2
    assert board[0][0].id == players[1].id
