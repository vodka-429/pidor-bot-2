"""Раз на раз (coin duel) и вызов ментов (police)."""
import logging
import secrets
from datetime import date, datetime, timedelta
from html import escape as html_escape
from typing import Dict, Iterable, List, Optional, Tuple

from sqlmodel import select

from bot.app.models import (
    DEPOSIT_STATUS_OPEN,
    CoinDeposit,
    CoinDuel,
    Game,
    GamePlayer,
    GameResult,
    PoliceCall,
    TGUser,
    UserAchievement,
)
from bot.handlers.game.cbr_service import calculate_commission_amount
from bot.handlers.game.coin_service import add_coins, get_balances, get_open_deposit_amounts
from bot.handlers.game.config import get_config_by_game_id
from bot.handlers.game.deposit_service import (
    collect_deposit_part,
    get_arrested_deposit_ids,
    get_open_deposit,
)
from bot.handlers.game.shop_service import (
    calculate_next_day,
    can_afford,
    process_purchase,
    spend_coins,
)
from bot.handlers.game.text_static import (
    DEPOSIT_COLLECTED_LINE,
    DUEL_RESULT_HEADER,
    DUEL_RESULT_LINE,
    DUEL_TIE_LINE,
)
from bot.handlers.game.transfer_service import get_or_create_chat_bank

logger = logging.getLogger(__name__)

DUEL_STATUS_PENDING = "pending"
DUEL_STATUS_RESOLVED = "resolved"
DUEL_STATUS_CANCELLED = "cancelled"

# Фиксированные кнопки ставки (фильтруются по балансу и duel_max_stake)
DUEL_STAKE_OPTIONS = (2, 5, 10, 20)

POLICE_ACHIEVEMENT_CODE = "police_caller"


def _day_of_year(value: date) -> int:
    return value.timetuple().tm_yday


def get_duel_target_day(db_session, game_id: int, current_date: date, same_day: bool) -> Tuple[int, int]:
    """
    День разборки (year, day) для дуэли, созданной в current_date.

    Обычно — завтрашний день. В тестовом режиме same_day — сегодняшний,
    если сегодняшний розыгрыш в чате ещё не прошёл.
    """
    year, day = current_date.year, _day_of_year(current_date)
    if same_day:
        played = db_session.exec(
            select(GameResult).where(
                GameResult.game_id == game_id,
                GameResult.year == year,
                GameResult.day == day,
            )
        ).first()
        if played is None:
            return year, day
    return calculate_next_day(current_date, year)


def calc_leverage(challenger_balance: int, target_balance: int, max_leverage: int) -> int:
    """
    Множитель k в десятых долях (целочисленно): 25 означает ×2.5.

    k = target_balance / challenger_balance, округление вниз до десятых,
    не больше max_leverage. Для богатой цели k >= 1 по построению.
    """
    cap = max_leverage * 10
    if challenger_balance <= 0:
        return cap
    return min(target_balance * 10 // challenger_balance, cap)


def format_leverage(k10: int) -> str:
    """25 → '2.5', 30 → '3'."""
    whole, tenth = divmod(k10, 10)
    return str(whole) if tenth == 0 else f"{whole}.{tenth}"


def calc_target_stake(stake: int, k10: int, target_balance: int) -> int:
    """Ставка цели: ceil(k * stake), но не больше того, что у цели можно взять (кошелёк + вклад)."""
    return min(-(-k10 * stake // 10), target_balance)


def _is_active_player(db_session, game_id: int, user_id: int) -> bool:
    link = db_session.exec(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    ).first()
    return link is not None and link.is_active


def get_police_call(db_session, game_id: int, year: int, day: int) -> Optional[PoliceCall]:
    return db_session.exec(
        select(PoliceCall).where(
            PoliceCall.game_id == game_id,
            PoliceCall.year == year,
            PoliceCall.day == day,
        )
    ).first()


def get_challenger_duel_today(db_session, game_id: int, challenger_id: int, current_date: date) -> Optional[CoinDuel]:
    return db_session.exec(
        select(CoinDuel).where(
            CoinDuel.game_id == game_id,
            CoinDuel.challenger_id == challenger_id,
            CoinDuel.created_year == current_date.year,
            CoinDuel.created_day == _day_of_year(current_date),
        )
    ).first()


def get_target_duel(db_session, game_id: int, target_id: int, year: int, day: int) -> Optional[CoinDuel]:
    return db_session.exec(
        select(CoinDuel).where(
            CoinDuel.game_id == game_id,
            CoinDuel.target_id == target_id,
            CoinDuel.year == year,
            CoinDuel.day == day,
        )
    ).first()


def get_pending_duels(db_session, game_id: int, year: int, day: int) -> List[CoinDuel]:
    return list(db_session.exec(
        select(CoinDuel).where(
            CoinDuel.game_id == game_id,
            CoinDuel.year == year,
            CoinDuel.day == day,
            CoinDuel.status == DUEL_STATUS_PENDING,
        ).order_by(CoinDuel.id).with_for_update()
    ).all())


def get_duel_wealths(db_session, game_id: int, user_ids: Iterable[int]) -> Dict[int, int]:
    """Богатство игроков для дуэли: баланс за всё время + тело открытого вклада."""
    wealths = get_balances(db_session, game_id, user_ids)
    if not wealths:
        return wealths
    for user_id, amount in get_open_deposit_amounts(db_session, game_id).items():
        if user_id in wealths:
            wealths[user_id] += amount
    return wealths


def get_target_capacity(
    db_session, game_id: int, target_id: int, today: date
) -> Tuple[int, Optional[CoinDeposit], int]:
    """
    Сколько можно взять у цели: (кошелёк, открытый вклад, сумма вклада, доступная для ареста).

    Вклад, уже арестованный другой дуэлью, второй раз не арестовывается: доступен только кошелёк.
    """
    wallet = max(get_balances(db_session, game_id, [target_id]).get(target_id, 0), 0)
    deposit = get_open_deposit(db_session, game_id, target_id)
    deposit_available = 0
    if deposit is not None and deposit.id not in get_arrested_deposit_ids(db_session, game_id, today):
        deposit_available = deposit.amount
    return wallet, deposit, deposit_available


def get_duel_targets(
    db_session,
    game_id: int,
    challenger_id: int,
    active_players: Iterable[TGUser],
) -> List[Tuple[TGUser, int]]:
    """
    Активные игроки со строго большим богатством, чем у вызывающего (по убыванию).

    Богатство — баланс за всё время плюс тело открытого вклада.
    """
    players = [player for player in active_players if player.id is not None]
    wealths = get_duel_wealths(
        db_session, game_id, [player.id for player in players] + [challenger_id]
    )
    challenger_wealth = wealths.get(challenger_id, 0)
    targets = [
        (player, wealths.get(player.id, 0))
        for player in players
        if player.id != challenger_id and wealths.get(player.id, 0) > challenger_wealth
    ]
    targets.sort(key=lambda item: item[1], reverse=True)
    return targets


def get_stake_options(challenger_balance: int, min_stake: int, max_stake: int) -> List[int]:
    """Доступные кнопки ставок: 2 / 5 / 10 / 20 в пределах лимитов и кошелька (вклад в ставку вызывающего не идёт)."""
    return [
        amount for amount in DUEL_STAKE_OPTIONS
        if min_stake <= amount <= max_stake and amount <= challenger_balance
    ]


def create_duel(
    db_session,
    game_id: int,
    challenger_id: int,
    target_id: int,
    stake: int,
    current_date: date,
) -> Tuple[bool, str, Optional[CoinDuel]]:
    """
    Создать дуэль: ставки списываются сразу, разборка — на розыгрыше дня цели.

    Если у цели не хватает койнов в кошельке, недостача записывается в target_deposit_part:
    деньги не двигаются, но вклад цели арестован (его нельзя снять и он не выплачивается)
    до разборки.

    Returns:
        (success, reason, duel). Коды ошибок: feature_disabled, not_registered,
        police_on_duty, already_challenged, target_busy, target_not_richer,
        invalid_stake, insufficient_funds.
    """
    config = get_config_by_game_id(db_session, game_id)
    c = config.constants
    if not c.duel_enabled:
        return False, "feature_disabled", None

    if not _is_active_player(db_session, game_id, challenger_id):
        return False, "not_registered", None
    if not _is_active_player(db_session, game_id, target_id):
        return False, "target_not_richer", None

    # Сериализуем дуэли и вызовы ментов одного чата.
    db_session.exec(select(Game).where(Game.id == game_id).with_for_update()).first()

    fight_year, fight_day = get_duel_target_day(db_session, game_id, current_date, c.duel_same_day)
    if get_police_call(db_session, game_id, fight_year, fight_day) is not None:
        return False, "police_on_duty", None
    if get_challenger_duel_today(db_session, game_id, challenger_id, current_date) is not None:
        return False, "already_challenged", None
    if get_target_duel(db_session, game_id, target_id, fight_year, fight_day) is not None:
        return False, "target_busy", None

    created_year = current_date.year
    wealths = get_duel_wealths(db_session, game_id, [challenger_id, target_id])
    challenger_wealth = wealths.get(challenger_id, 0)
    target_wealth = wealths.get(target_id, 0)
    if challenger_id == target_id or target_wealth <= challenger_wealth:
        return False, "target_not_richer", None

    # Ставка вызывающего берётся только из кошелька, вклад в ней не участвует.
    challenger_wallet = get_balances(db_session, game_id, [challenger_id]).get(challenger_id, 0)
    if stake < c.transfer_min_amount or stake > c.duel_max_stake:
        return False, "invalid_stake", None
    if stake > challenger_wallet or not can_afford(db_session, game_id, challenger_id, stake):
        return False, "insufficient_funds", None

    # Ставка цели: сначала кошелёк, недостача арестовывает вклад до разборки.
    target_wallet, target_deposit, deposit_available = get_target_capacity(
        db_session, game_id, target_id, current_date
    )
    k10 = calc_leverage(challenger_wealth, target_wealth, c.duel_max_leverage)
    target_stake = calc_target_stake(stake, k10, target_wallet + deposit_available)
    if target_stake <= 0:
        return False, "insufficient_funds", None
    wallet_part = min(target_stake, target_wallet)
    deposit_part = target_stake - wallet_part

    spend_coins(db_session, game_id, challenger_id, stake, created_year, "duel_stake", auto_commit=False)
    if wallet_part > 0:
        spend_coins(db_session, game_id, target_id, wallet_part, created_year, "duel_stake", auto_commit=False)
    duel = CoinDuel(
        game_id=game_id,
        challenger_id=challenger_id,
        target_id=target_id,
        created_year=created_year,
        created_day=_day_of_year(current_date),
        year=fight_year,
        day=fight_day,
        challenger_stake=stake,
        target_stake=target_stake,
        target_deposit_id=target_deposit.id if deposit_part > 0 else None,
        target_deposit_part=deposit_part,
        status=DUEL_STATUS_PENDING,
    )
    db_session.add(duel)
    db_session.commit()
    db_session.refresh(duel)
    logger.info(
        "Duel created: game=%s challenger=%s target=%s stakes=%s/%s fight=%s-%s",
        game_id, challenger_id, target_id, stake, target_stake, fight_year, fight_day,
    )
    return True, "success", duel


def roll_die() -> int:
    return secrets.randbelow(6) + 1


def calc_duel_settlement(duel: CoinDuel, winner_id: int, collected: int) -> Tuple[int, int, int]:
    """
    Расчёт выплаты дуэли: (own, winnings, fee).

    own — собственная ставка победителя (возвращается целиком), winnings — то, что реально
    пришло от проигравшего, fee — комиссия с выигрыша (не больше самого выигрыша, 0 при нулевом).
    Победителю достаётся own + winnings - fee.
    """
    deposit_part = duel.target_deposit_part or 0
    if winner_id == duel.challenger_id:
        own = duel.challenger_stake
        winnings = duel.target_stake - deposit_part + collected
    else:
        own = duel.target_stake - deposit_part
        winnings = duel.challenger_stake
    fee = min(calculate_commission_amount(winnings), winnings) if winnings > 0 else 0
    return own, winnings, fee


def resolve_duels_for_day(db_session, game_id: int, year: int, day: int, pay_year: int) -> List[CoinDuel]:
    """
    Разыграть все ожидающие дуэли дня. Без коммита — коммитит розыгрыш.

    Победитель забирает свою ставку и выигрыш за вычетом комиссии с выигрыша, комиссия уходит в банк чата.
    Блокирует строку Game, как create_duel и call_police, чтобы менты или новая
    дуэль не пересеклись с розыгрышем (двойная выплата).
    """
    db_session.exec(select(Game).where(Game.id == game_id).with_for_update()).first()
    duels = get_pending_duels(db_session, game_id, year, day)
    if not duels:
        return []

    bank = get_or_create_chat_bank(db_session, game_id, auto_commit=False)
    now = datetime.utcnow()
    for duel in duels:
        challenger_roll, target_roll = roll_die(), roll_die()
        ties = 0
        while challenger_roll == target_roll:
            ties += 1
            challenger_roll, target_roll = roll_die(), roll_die()

        winner_id = duel.challenger_id if challenger_roll > target_roll else duel.target_id
        # Часть ставки цели с вклада в банк дуэли не вносилась: она уйдёт в него, только если
        # цель проиграла (коллекторы закрывают вклад). Если цель выиграла, арест просто снимается.
        deposit_part = duel.target_deposit_part or 0
        collected = 0
        if deposit_part > 0 and winner_id == duel.challenger_id and duel.target_deposit_id is not None:
            deposit = db_session.get(CoinDeposit, duel.target_deposit_id)
            if deposit is not None and deposit.status == DEPOSIT_STATUS_OPEN:
                collected = collect_deposit_part(db_session, deposit, deposit_part, pay_year, now)
        own, winnings, fee = calc_duel_settlement(duel, winner_id, collected)
        payout = own + winnings - fee
        if payout > 0:
            add_coins(db_session, game_id, winner_id, payout, pay_year, "duel_win", auto_commit=False)

        duel.challenger_roll = challenger_roll
        duel.target_roll = target_roll
        duel.tie_count = ties
        duel.winner_id = winner_id
        duel.commission = fee
        duel.status = DUEL_STATUS_RESOLVED
        duel.resolved_at = now
        db_session.add(duel)
        bank.balance += fee
        logger.info(
            "Duel %s resolved: rolls %s:%s ties=%s winner=%s winnings=%s fee=%s",
            duel.id, challenger_roll, target_roll, ties, winner_id, winnings, fee,
        )

    bank.updated_at = now
    db_session.add(bank)
    return duels


def _user_name(user: Optional[TGUser]) -> str:
    return html_escape(user.full_username()) if user is not None else "?"


def format_duel_result_html(duel: CoinDuel, challenger: TGUser, target: TGUser) -> str:
    """HTML-строка результата одной дуэли (без общего заголовка)."""
    challenger_name = _user_name(challenger)
    target_name = _user_name(target)
    if duel.winner_id == duel.challenger_id:
        winner_name, loser_name = challenger_name, target_name
        winner_roll, loser_roll = duel.challenger_roll, duel.target_roll
    else:
        winner_name, loser_name = target_name, challenger_name
        winner_roll, loser_roll = duel.target_roll, duel.challenger_roll
    deposit_part = duel.target_deposit_part or 0
    target_won = duel.winner_id == duel.target_id
    text = DUEL_RESULT_LINE.format(
        winner=winner_name,
        winner_roll=winner_roll,
        loser=loser_name,
        loser_roll=loser_roll,
        # Если цель выиграла, арестованная часть в банк дуэли не входила
        # Сумма на руки победителю (с допущением collected == deposit_part)
        pot=duel.challenger_stake + duel.target_stake - (deposit_part if target_won else 0) - duel.commission,
        fee=duel.commission,
    )
    if duel.tie_count:
        text = f"{DUEL_TIE_LINE}\n{text}"
    if deposit_part > 0 and not target_won:
        text += "\n" + DEPOSIT_COLLECTED_LINE.format(target=target_name, part=deposit_part)
    return text


def format_duels_block(db_session, duels: List[CoinDuel]) -> str:
    """Все результаты дуэлей одним блоком (пустая строка, если дуэлей нет)."""
    if not duels:
        return ""
    lines = [DUEL_RESULT_HEADER]
    for duel in duels:
        challenger = db_session.get(TGUser, duel.challenger_id)
        target = db_session.get(TGUser, duel.target_id)
        lines.append(format_duel_result_html(duel, challenger, target))
    return "\n".join(lines)


def get_police_cooldown_end(db_session, game_id: int, caller_id: int, cooldown_days: int) -> Optional[date]:
    """Дата, с которой игрок снова может вызвать ментов (None — кулдауна не было)."""
    last_call = db_session.exec(
        select(PoliceCall).where(
            PoliceCall.game_id == game_id,
            PoliceCall.caller_id == caller_id,
        ).order_by(PoliceCall.call_date.desc())
    ).first()
    if last_call is None:
        return None
    return last_call.call_date + timedelta(days=cooldown_days)


def call_police(
    db_session,
    game_id: int,
    caller_id: int,
    current_date: date,
) -> Tuple[bool, str, List[CoinDuel], Optional[UserAchievement]]:
    """
    Вызвать ментов: отменить все дуэли дня разборок и вернуть обе ставки без комиссии.

    Returns:
        (success, reason, refunded_duels, achievement). Коды ошибок: feature_disabled,
        not_registered, already_called, cooldown:{YYYY-MM-DD}, insufficient_funds.
    """
    config = get_config_by_game_id(db_session, game_id)
    c = config.constants
    if not c.duel_enabled:
        return False, "feature_disabled", [], None
    if not _is_active_player(db_session, game_id, caller_id):
        return False, "not_registered", [], None

    db_session.exec(select(Game).where(Game.id == game_id).with_for_update()).first()

    fight_year, fight_day = get_duel_target_day(db_session, game_id, current_date, c.duel_same_day)
    if get_police_call(db_session, game_id, fight_year, fight_day) is not None:
        return False, "already_called", [], None

    cooldown_end = get_police_cooldown_end(db_session, game_id, caller_id, c.police_cooldown_days)
    if cooldown_end is not None and current_date < cooldown_end:
        return False, f"cooldown:{cooldown_end.isoformat()}", [], None

    success, reason, _ = process_purchase(
        db_session, game_id, caller_id, c.police_price, current_date.year, "police"
    )
    if not success:
        return False, reason, [], None

    duels = get_pending_duels(db_session, game_id, fight_year, fight_day)
    now = datetime.utcnow()
    for duel in duels:
        add_coins(
            db_session, game_id, duel.challenger_id, duel.challenger_stake,
            duel.created_year, "duel_refund", auto_commit=False,
        )
        # Часть ставки цели с вклада не списывалась: возвращать нечего, арест снимается отменой.
        target_refund = duel.target_stake - (duel.target_deposit_part or 0)
        if target_refund > 0:
            add_coins(
                db_session, game_id, duel.target_id, target_refund,
                duel.created_year, "duel_refund", auto_commit=False,
            )
        duel.status = DUEL_STATUS_CANCELLED
        duel.resolved_at = now
        db_session.add(duel)

    db_session.add(PoliceCall(
        game_id=game_id,
        caller_id=caller_id,
        year=fight_year,
        day=fight_day,
        call_date=current_date,
        price=c.police_price,
        refunded_duels=len(duels),
    ))

    achievement = None
    if c.achievements_enabled:
        from bot.handlers.game.achievement_service import award_achievement, has_achievement
        if not has_achievement(db_session, game_id, caller_id, POLICE_ACHIEVEMENT_CODE):
            achievement = award_achievement(
                db_session, game_id, caller_id, POLICE_ACHIEVEMENT_CODE, current_date.year
            )

    db_session.commit()
    logger.info(
        "Police called: game=%s caller=%s fight=%s-%s refunded_duels=%s",
        game_id, caller_id, fight_year, fight_day, len(duels),
    )
    return True, "success", duels, achievement
