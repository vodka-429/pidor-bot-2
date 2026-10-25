"""Tests for «Раз на раз» (coin duel) and police services."""
from datetime import date
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from bot.app.models import (
    ChatBank,
    CoinDuel,
    Game,
    GamePlayer,
    GameResult,
    PidorCoinTransaction,
    PoliceCall,
    TGUser,
    UserAchievement,
)
from bot.handlers.game.coin_service import get_balance
from bot.handlers.game.config import ChatConfig, GameConstants
from bot.handlers.game.duel_service import (
    calc_leverage,
    calc_target_stake,
    call_police,
    calc_duel_settlement,
    create_duel,
    format_duel_result_html,
    format_duels_block,
    format_leverage,
    get_duel_target_day,
    get_duel_targets,
    get_stake_options,
    resolve_duels_for_day,
)

YEAR = 2026
TODAY = date(2026, 6, 15)          # day 166
TODAY_DAY = 166
TOMORROW_DAY = 167
# Балансы игроков 0..4 (все транзакции в YEAR)
SEED = [10, 25, 40, 100, 5]


@pytest.fixture
def duel_session():
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
                tg_id=2000 + index,
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
        session.commit()
        yield session, game, players


def _config(**overrides):
    values = {"duel_enabled": True}
    values.update(overrides)
    return ChatConfig(chat_id=-1001, constants=GameConstants(**values))


@pytest.fixture
def duel_env():
    """Включённая фича и фиксированная комиссия (без запросов к ЦБ)."""
    config = _config()
    with patch(
        "bot.handlers.game.duel_service.get_config_by_game_id", return_value=config,
    ), patch(
        "bot.handlers.game.duel_service.calculate_commission_amount",
        side_effect=lambda amount: max(1, amount // 10),
    ), patch(
        "bot.handlers.game.shop_service.calculate_commission_amount",
        side_effect=lambda amount: max(1, amount // 10),
    ):
        yield config


def _bank_balance(session, game_id):
    bank = session.exec(select(ChatBank).where(ChatBank.game_id == game_id)).first()
    return bank.balance if bank else 0


# --- pure math ---

@pytest.mark.unit
def test_calc_leverage_below_cap_and_capped():
    assert calc_leverage(10, 11, 3) == 11          # ×1.1
    assert calc_leverage(10, 25, 3) == 25          # ×2.5
    assert calc_leverage(10, 30, 3) == 30          # exactly ×3
    assert calc_leverage(10, 1000, 3) == 30        # capped
    assert calc_leverage(3, 10, 3) == 30           # 3.33 → capped at 3


@pytest.mark.unit
def test_calc_leverage_rounds_down_to_tenths():
    assert calc_leverage(3, 4, 3) == 13            # 1.333 → 1.3


@pytest.mark.unit
def test_format_leverage():
    assert format_leverage(30) == "3"
    assert format_leverage(25) == "2.5"
    assert format_leverage(11) == "1.1"


@pytest.mark.unit
def test_calc_target_stake_ceil_and_cap():
    assert calc_target_stake(5, 25, 100) == 13     # 12.5 → 13
    assert calc_target_stake(10, 30, 100) == 30
    assert calc_target_stake(2, 11, 100) == 3      # 2.2 → 3
    assert calc_target_stake(20, 30, 45) == 45     # capped by target balance


@pytest.mark.unit
def test_get_stake_options_filters_by_balance_and_limits():
    assert get_stake_options(100, 2, 20) == [2, 5, 10, 20]
    assert get_stake_options(7, 2, 20) == [2, 5]
    assert get_stake_options(1, 2, 20) == []
    assert get_stake_options(100, 2, 10) == [2, 5, 10]


# --- target day ---

@pytest.mark.unit
def test_target_day_is_tomorrow_without_same_day(duel_session):
    session, game, _ = duel_session
    assert get_duel_target_day(session, game.id, TODAY, False) == (YEAR, TOMORROW_DAY)


@pytest.mark.unit
def test_target_day_same_day_before_and_after_draw(duel_session):
    session, game, players = duel_session
    assert get_duel_target_day(session, game.id, TODAY, True) == (YEAR, TODAY_DAY)
    session.add(GameResult(game_id=game.id, winner_id=players[0].id, year=YEAR, day=TODAY_DAY))
    session.commit()
    assert get_duel_target_day(session, game.id, TODAY, True) == (YEAR, TOMORROW_DAY)


@pytest.mark.unit
def test_target_day_new_year(duel_session):
    session, game, _ = duel_session
    assert get_duel_target_day(session, game.id, date(2026, 12, 31), False) == (2027, 1)


# --- targets ---

@pytest.mark.unit
def test_duel_targets_only_strictly_richer(duel_session):
    session, game, players = duel_session
    targets = get_duel_targets(session, game.id, players[1].id, players)
    assert [player.id for player, _ in targets] == [players[3].id, players[2].id]
    assert [balance for _, balance in targets] == [100, 40]


def _add_history(session, game, player, amount, year=YEAR - 1):
    session.add(PidorCoinTransaction(
        game_id=game.id, user_id=player.id, amount=amount, year=year, reason="seed",
    ))
    session.commit()


@pytest.mark.unit
def test_duel_targets_count_last_year_coins(duel_session):
    session, game, players = duel_session
    _add_history(session, game, players[0], 30)   # 10 за год, 40 за всё время
    targets = get_duel_targets(session, game.id, players[1].id, players)
    balances = {player.id: balance for player, balance in targets}
    assert balances == {players[3].id: 100, players[2].id: 40, players[0].id: 40}
    assert targets[0][0].id == players[3].id


@pytest.mark.unit
def test_duel_leverage_uses_all_time_balance(duel_session, duel_env):
    session, game, players = duel_session
    _add_history(session, game, players[0], 30)
    # 25 против 40 → ×1.6, ставка цели ceil(1.6 * 10) = 16
    success, reason, duel = create_duel(session, game.id, players[1].id, players[0].id, 10, TODAY)
    assert (success, reason) == (True, "success")
    assert duel.target_stake == 16
    assert get_balance(session, game.id, players[0].id) == 40 - 16


@pytest.mark.unit
def test_duel_negative_history_makes_target_poorer(duel_session, duel_env):
    session, game, players = duel_session
    _add_history(session, game, players[1], -20)   # 25 за год, но 5 за всё время
    targets = get_duel_targets(session, game.id, players[4].id, players)
    assert players[1].id not in [player.id for player, _ in targets]
    assert create_duel(session, game.id, players[4].id, players[1].id, 2, TODAY)[1] == "target_not_richer"


@pytest.mark.unit
def test_duel_across_year_boundary_uses_all_time_balance(duel_session, duel_env):
    session, game, players = duel_session
    challenger, target = players[0], players[1]
    success, _, duel = create_duel(session, game.id, challenger.id, target.id, 5, date(2026, 12, 31))
    assert success is True
    assert (duel.year, duel.day) == (2027, 1)

    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=[5, 0]):
        results = resolve_duels_for_day(session, game.id, 2027, 1, 2027)
    session.commit()

    assert results[0].winner_id == challenger.id
    assert get_balance(session, game.id, challenger.id) == 5 + 17
    win = session.exec(select(PidorCoinTransaction).where(
        PidorCoinTransaction.user_id == challenger.id,
        PidorCoinTransaction.reason == "duel_win",
    )).one()
    assert win.year == 2027


# --- create_duel ---

@pytest.mark.unit
def test_create_duel_success_spends_both_stakes(duel_session, duel_env):
    session, game, players = duel_session
    challenger, target = players[0], players[1]   # 10 vs 25 → ×2.5
    success, reason, duel = create_duel(session, game.id, challenger.id, target.id, 5, TODAY)

    assert (success, reason) == (True, "success")
    assert (duel.year, duel.day) == (YEAR, TOMORROW_DAY)
    assert (duel.challenger_stake, duel.target_stake) == (5, 13)
    assert duel.status == "pending"
    assert get_balance(session, game.id, challenger.id) == 5
    assert get_balance(session, game.id, target.id) == 12


@pytest.mark.unit
def test_create_duel_target_stake_capped_by_leverage(duel_session, duel_env):
    session, game, players = duel_session
    success, _, duel = create_duel(session, game.id, players[0].id, players[3].id, 10, TODAY)
    assert success is True
    assert duel.target_stake == 30   # 100/10 → capped ×3


@pytest.mark.unit
def test_create_duel_rejects_not_richer_target(duel_session, duel_env):
    session, game, players = duel_session
    assert create_duel(session, game.id, players[1].id, players[0].id, 5, TODAY)[1] == "target_not_richer"
    assert create_duel(session, game.id, players[1].id, players[1].id, 5, TODAY)[1] == "target_not_richer"


@pytest.mark.unit
def test_create_duel_one_challenge_per_day(duel_session, duel_env):
    session, game, players = duel_session
    assert create_duel(session, game.id, players[0].id, players[1].id, 2, TODAY)[0] is True
    assert create_duel(session, game.id, players[0].id, players[2].id, 2, TODAY)[1] == "already_challenged"


@pytest.mark.unit
def test_create_duel_target_busy(duel_session, duel_env):
    session, game, players = duel_session
    assert create_duel(session, game.id, players[0].id, players[3].id, 2, TODAY)[0] is True
    assert create_duel(session, game.id, players[4].id, players[3].id, 2, TODAY)[1] == "target_busy"


@pytest.mark.unit
def test_create_duel_blocked_after_police(duel_session, duel_env):
    session, game, players = duel_session
    assert call_police(session, game.id, players[3].id, TODAY)[0] is True
    assert create_duel(session, game.id, players[0].id, players[1].id, 2, TODAY)[1] == "police_on_duty"


@pytest.mark.unit
def test_create_duel_stake_limits(duel_session, duel_env):
    session, game, players = duel_session
    assert create_duel(session, game.id, players[2].id, players[3].id, 1, TODAY)[1] == "invalid_stake"
    assert create_duel(session, game.id, players[2].id, players[3].id, 21, TODAY)[1] == "invalid_stake"


@pytest.mark.unit
def test_create_duel_stake_above_balance(duel_session, duel_env):
    session, game, players = duel_session
    # Игрок 4 имеет 5 койнов
    assert create_duel(session, game.id, players[4].id, players[0].id, 10, TODAY)[1] == "insufficient_funds"


@pytest.mark.unit
def test_create_duel_feature_disabled(duel_session):
    session, game, players = duel_session
    with patch(
        "bot.handlers.game.duel_service.get_config_by_game_id",
        return_value=_config(duel_enabled=False),
    ):
        assert create_duel(session, game.id, players[0].id, players[1].id, 2, TODAY)[1] == "feature_disabled"
    assert session.exec(select(CoinDuel)).all() == []


@pytest.mark.unit
def test_create_duel_same_day_mode_binds_to_today(duel_session):
    session, game, players = duel_session
    with patch(
        "bot.handlers.game.duel_service.get_config_by_game_id",
        return_value=_config(duel_same_day=True),
    ):
        success, _, duel = create_duel(session, game.id, players[0].id, players[1].id, 2, TODAY)
    assert success is True
    assert (duel.year, duel.day) == (YEAR, TODAY_DAY)


# --- resolve ---

@pytest.mark.unit
def test_resolve_pays_winner_pot_minus_fee(duel_session, duel_env):
    session, game, players = duel_session
    challenger, target = players[0], players[1]
    _, _, duel = create_duel(session, game.id, challenger.id, target.id, 5, TODAY)   # выигрыш 13, fee 1

    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=[5, 0]):
        results = resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR)
    session.commit()

    assert len(results) == 1
    resolved = results[0]
    assert (resolved.challenger_roll, resolved.target_roll) == (6, 1)
    assert resolved.winner_id == challenger.id
    assert resolved.status == "resolved"
    assert resolved.commission == 1
    assert get_balance(session, game.id, challenger.id) == 5 + 17
    assert get_balance(session, game.id, target.id) == 12
    assert _bank_balance(session, game.id) == 1


@pytest.mark.unit
def test_format_duel_result_challenger_wins(duel_session, duel_env):
    session, game, players = duel_session
    create_duel(session, game.id, players[0].id, players[1].id, 5, TODAY)
    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=[5, 0]):
        results = resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR)
    duel = results[0]
    assert duel.winner_id == players[0].id
    text = format_duel_result_html(duel, players[0], players[1])
    assert text == "player0 🎲6 дал пизды player1 🎲1 и уходит с 17 💰 (−1 в банк)"


@pytest.mark.unit
def test_format_duel_result_escapes_html(duel_session, duel_env):
    session, game, players = duel_session
    create_duel(session, game.id, players[0].id, players[1].id, 5, TODAY)
    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=[5, 0]):
        results = resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR)
    players[0].username = "<b>x</b>"
    text = format_duel_result_html(results[0], players[0], players[1])
    assert "<b>x</b>" not in text
    assert "&lt;b&gt;x&lt;/b&gt;" in text


@pytest.mark.unit
def test_resolve_rerolls_on_tie(duel_session, duel_env):
    session, game, players = duel_session
    create_duel(session, game.id, players[0].id, players[1].id, 5, TODAY)
    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=[2, 2, 3, 3, 0, 4]):
        results = resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR)
    duel = results[0]
    assert duel.tie_count == 2
    assert (duel.challenger_roll, duel.target_roll) == (1, 5)
    assert duel.winner_id == players[1].id
    text = format_duel_result_html(duel, players[0], players[1])
    assert text.startswith("🎲 Ничья, перебрасывают…\n")
    assert "player1 🎲5 дал пизды player0 🎲1 и уходит с 17 💰 (−1 в банк)" in text
    assert "Раз на раз за гаражами" not in text

    block = format_duels_block(session, results)
    assert block.startswith("🥊 <b>Раз на раз за гаражами:</b>\n🎲 Ничья, перебрасывают…\n")
    assert block.count("Раз на раз за гаражами") == 1


@pytest.mark.unit
def test_resolve_ignores_other_days_and_resolved(duel_session, duel_env):
    session, game, players = duel_session
    create_duel(session, game.id, players[0].id, players[1].id, 5, TODAY)
    assert resolve_duels_for_day(session, game.id, YEAR, TODAY_DAY, YEAR) == []

    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=[5, 0]):
        assert len(resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR)) == 1
    session.commit()
    assert resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR) == []


def _duel(challenger_stake, target_stake, deposit_part=0):
    return CoinDuel(
        game_id=1, challenger_id=1, target_id=2, created_year=YEAR, created_day=1,
        year=YEAR, day=2, challenger_stake=challenger_stake, target_stake=target_stake,
        target_deposit_part=deposit_part,
    )


@pytest.mark.unit
def test_calc_duel_settlement_challenger_wins(duel_env):
    # Выигрыш 60, комиссия 6, своя ставка 20 возвращается целиком
    assert calc_duel_settlement(_duel(20, 60), 1, 0) == (20, 60, 6)


@pytest.mark.unit
def test_calc_duel_settlement_target_wins(duel_env):
    # Выигрыш 20, комиссия 2, своя ставка цели 60 возвращается целиком
    assert calc_duel_settlement(_duel(20, 60), 2, 0) == (60, 20, 2)


@pytest.mark.unit
def test_calc_duel_settlement_with_deposit_part(duel_env):
    # Часть цели с вклада: проиграла - собрано 22, выиграла - арест снят и выигрыша с неё нет
    assert calc_duel_settlement(_duel(20, 52, 22), 1, 22) == (20, 52, 5)
    assert calc_duel_settlement(_duel(20, 52, 22), 1, 0) == (20, 30, 3)
    assert calc_duel_settlement(_duel(20, 52, 22), 2, 0) == (30, 20, 2)


@pytest.mark.unit
def test_calc_duel_settlement_zero_winnings_has_no_fee(duel_env):
    # Вся ставка цели - с вклада, который не удалось собрать: выигрыша нет, комиссия 0, без исключения
    assert calc_duel_settlement(_duel(10, 20, 20), 1, 0) == (10, 0, 0)


@pytest.mark.unit
def test_calc_duel_settlement_fee_not_above_winnings():
    with patch("bot.handlers.game.duel_service.calculate_commission_amount", return_value=5):
        assert calc_duel_settlement(_duel(2, 2), 1, 0) == (2, 2, 2)


def _resolve_custom(session, game, players, challenger_stake, target_stake, rolls):
    for player, amount in ((players[0], challenger_stake), (players[1], target_stake)):
        session.add(PidorCoinTransaction(
            game_id=game.id, user_id=player.id, amount=-amount, year=YEAR, reason="duel_stake",
        ))
    session.add(CoinDuel(
        game_id=game.id, challenger_id=players[0].id, target_id=players[1].id,
        created_year=YEAR, created_day=TODAY_DAY, year=YEAR, day=TOMORROW_DAY,
        challenger_stake=challenger_stake, target_stake=target_stake,
    ))
    session.commit()
    before = (get_balance(session, game.id, players[0].id), get_balance(session, game.id, players[1].id))
    with patch("bot.handlers.game.duel_service.secrets.randbelow", side_effect=rolls):
        results = resolve_duels_for_day(session, game.id, YEAR, TOMORROW_DAY, YEAR)
    session.commit()
    return results[0], before


@pytest.mark.unit
def test_resolve_20_vs_60_challenger_wins_pays_tax_on_winnings(duel_session, duel_env):
    session, game, players = duel_session
    duel, before = _resolve_custom(session, game, players, 20, 60, [5, 0])
    assert (duel.winner_id, duel.commission) == (players[0].id, 6)
    assert get_balance(session, game.id, players[0].id) == before[0] + 20 + 60 - 6
    assert get_balance(session, game.id, players[1].id) == before[1]
    assert _bank_balance(session, game.id) == 6
    assert "уходит с 74 💰 (−6 в банк)" in format_duel_result_html(duel, players[0], players[1])


@pytest.mark.unit
def test_resolve_20_vs_60_target_wins_pays_tax_on_winnings(duel_session, duel_env):
    session, game, players = duel_session
    duel, before = _resolve_custom(session, game, players, 20, 60, [0, 5])
    assert (duel.winner_id, duel.commission) == (players[1].id, 2)
    assert get_balance(session, game.id, players[1].id) == before[1] + 60 + 20 - 2
    assert get_balance(session, game.id, players[0].id) == before[0]
    assert _bank_balance(session, game.id) == 2
    assert "уходит с 78 💰 (−2 в банк)" in format_duel_result_html(duel, players[0], players[1])


@pytest.mark.unit
def test_resolve_min_stake_two_fee_not_above_winnings(duel_session, duel_env):
    session, game, players = duel_session
    duel, before = _resolve_custom(session, game, players, 2, 2, [5, 0])
    # Мок-комиссия max(1, 2 // 10) = 1: выигрыш 2, на руки 2 + 2 - 1
    assert duel.commission == 1
    assert get_balance(session, game.id, players[0].id) == before[0] + 3


# --- police ---

@pytest.mark.unit
def test_police_refunds_all_duels_without_commission(duel_session, duel_env):
    session, game, players = duel_session
    create_duel(session, game.id, players[0].id, players[1].id, 5, TODAY)
    create_duel(session, game.id, players[4].id, players[2].id, 5, TODAY)

    success, reason, refunded, achievement = call_police(session, game.id, players[3].id, TODAY)

    assert (success, reason) == (True, "success")
    assert len(refunded) == 2
    for index, amount in enumerate(SEED[:3]):
        assert get_balance(session, game.id, players[index].id) == amount
    assert get_balance(session, game.id, players[4].id) == SEED[4]
    assert get_balance(session, game.id, players[3].id) == 100 - 30
    statuses = {duel.status for duel in session.exec(select(CoinDuel)).all()}
    assert statuses == {"cancelled"}
    # В банк уходит только комиссия магазина с цены вызова (30 // 10 = 3)
    assert _bank_balance(session, game.id) == 3
    call = session.exec(select(PoliceCall)).one()
    assert (call.year, call.day, call.refunded_duels) == (YEAR, TOMORROW_DAY, 2)
    assert achievement is not None and achievement.achievement_code == "police_caller"


@pytest.mark.unit
def test_police_once_per_day_in_chat(duel_session, duel_env):
    session, game, players = duel_session
    assert call_police(session, game.id, players[3].id, TODAY)[0] is True
    assert call_police(session, game.id, players[2].id, TODAY)[1] == "already_called"


@pytest.mark.unit
def test_police_personal_cooldown(duel_session, duel_env):
    session, game, players = duel_session
    assert call_police(session, game.id, players[3].id, TODAY)[0] is True
    reason = call_police(session, game.id, players[3].id, date(2026, 6, 20))[1]
    assert reason == "cooldown:2026-06-22"
    assert call_police(session, game.id, players[3].id, date(2026, 6, 22))[0] is True


@pytest.mark.unit
def test_police_insufficient_funds(duel_session, duel_env):
    session, game, players = duel_session
    assert call_police(session, game.id, players[0].id, TODAY)[1] == "insufficient_funds"
    assert session.exec(select(PoliceCall)).all() == []


@pytest.mark.unit
def test_police_achievement_once_and_no_coins(duel_session, duel_env):
    session, game, players = duel_session
    caller = players[3]
    first = call_police(session, game.id, caller.id, TODAY)[3]
    second = call_police(session, game.id, caller.id, date(2026, 6, 25))[3]

    assert first is not None
    assert second is None
    achievements = session.exec(select(UserAchievement)).all()
    assert len(achievements) == 1
    reasons = [tx.reason for tx in session.exec(
        select(PidorCoinTransaction).where(PidorCoinTransaction.user_id == caller.id)
    ).all()]
    assert "achievement_police_caller" not in reasons
