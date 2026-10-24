"""Вклады: койны под процент от ключевой ставки ЦБ, зафиксированный при открытии."""
import logging
from datetime import date, datetime, timedelta
from html import escape as html_escape
from typing import Dict, Iterable, List, Optional, Tuple

from sqlmodel import select

from bot.app.models import (
    DEPOSIT_STATUS_COLLECTED,
    DEPOSIT_STATUS_OPEN,
    DEPOSIT_STATUS_PAID,
    DEPOSIT_STATUS_WITHDRAWN,
    CoinDeposit,
    CoinDuel,
    Game,
    GamePlayer,
    TGUser,
)
from bot.handlers.game.cbr_service import get_key_rate
from bot.handlers.game.coin_service import add_coins, get_balance
from bot.handlers.game.config import get_config_by_game_id
from bot.handlers.game.shop_service import spend_coins
from bot.handlers.game.text_static import DEPOSIT_PAYOUT_HEADER, DEPOSIT_PAYOUT_LINE
from bot.handlers.game.transfer_service import get_or_create_chat_bank

logger = logging.getLogger(__name__)

# Срок вклада в днях -> доля 30-дневной ставки (числитель, знаменатель)
DEPOSIT_TERMS: Dict[int, Tuple[int, int]] = {
    7: (1, 4),
    14: (1, 2),
    30: (1, 1),
}

# Фиксированные кнопки сумм (фильтруются по минимуму, потолку, кошельку и банку)
DEPOSIT_AMOUNT_OPTIONS = (50, 100, 200)

DUEL_STATUS_PENDING = "pending"


def _day_of_year(value: date) -> int:
    return value.timetuple().tm_yday


def rate_to_bp(rate_percent: float) -> int:
    """Ключевая ставка в процентах -> сотые доли процента (21.0 -> 2100)."""
    return int(round(rate_percent * 100))


def calc_interest(amount: int, rate_bp: int, term_days: int) -> int:
    """
    Проценты за срок: amount * ставка * доля срока, округление до ближайшего целого
    (половина — вверх), без капитализации.

    Ставка ЦБ — игровая условность: это ставка за 30 дней, а не годовая.
    """
    numerator, denominator = DEPOSIT_TERMS[term_days]
    scale = denominator * 10000
    return (2 * amount * rate_bp * numerator + scale) // (2 * scale)


def calc_min_amount(rate_bp: int, term_days: int) -> Optional[int]:
    """Наименьшая сумма, при которой проценты не меньше 1 койна (None — ставка нулевая)."""
    if rate_bp <= 0:
        return None
    numerator, denominator = DEPOSIT_TERMS[term_days]
    # Округлённый процент >= 1 при amount * rate * доля >= 0.5 койна.
    divisor = 2 * rate_bp * numerator
    return max(-(-denominator * 10000 // divisor), 1)


def format_term_percent(rate_bp: int, term_days: int) -> str:
    """Процент за срок для кнопок: 2100 и 7 дней -> '5.2'."""
    numerator, denominator = DEPOSIT_TERMS[term_days]
    value = rate_bp * numerator / (denominator * 100)
    return f"{value:.1f}".rstrip("0").rstrip(".")


def format_rate(rate_bp: int) -> str:
    """2100 -> '21', 1650 -> '16.5'."""
    return f"{rate_bp / 100:.2f}".rstrip("0").rstrip(".")


def get_amount_options(
    rate_bp: int,
    term_days: int,
    max_amount: int,
    wallet: int,
    bank_free: int,
) -> Tuple[List[int], str]:
    """
    Суммы для кнопок: только те, проценты по которым банк может покрыть.

    Returns:
        (суммы по возрастанию, причина пустого списка). Причина: "" (список не пуст),
        "bank_empty" (банк не покрывает даже минимум), "insufficient_funds" (в кошельке
        меньше минимума), "rate_too_low" (минимум выше потолка или ставка нулевая).
    """
    min_amount = calc_min_amount(rate_bp, term_days)
    if min_amount is None or min_amount > max_amount:
        return [], "rate_too_low"
    if calc_interest(min_amount, rate_bp, term_days) > bank_free:
        return [], "bank_empty"
    cap = min(wallet, max_amount)
    if cap < min_amount:
        return [], "insufficient_funds"
    # Проценты растут вместе с суммой: ищем наибольшую сумму, которую покрывает банк.
    while cap > min_amount and calc_interest(cap, rate_bp, term_days) > bank_free:
        cap -= 1
    candidates = {min_amount, cap}
    candidates.update(amount for amount in DEPOSIT_AMOUNT_OPTIONS if min_amount <= amount <= cap)
    # Дубли скрываем: сумма с тем же процентом, что у меньшей показанной, не нужна.
    options: List[int] = []
    last_interest = -1
    for amount in sorted(candidates):
        interest = calc_interest(amount, rate_bp, term_days)
        if interest > last_interest:
            options.append(amount)
            last_interest = interest
    return options, ""


def get_open_deposit(db_session, game_id: int, user_id: int) -> Optional[CoinDeposit]:
    return db_session.exec(
        select(CoinDeposit).where(
            CoinDeposit.game_id == game_id,
            CoinDeposit.user_id == user_id,
            CoinDeposit.status == DEPOSIT_STATUS_OPEN,
        )
    ).first()


def _is_active_player(db_session, game_id: int, user_id: int) -> bool:
    link = db_session.exec(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    ).first()
    return link is not None and link.is_active


def get_arrested_deposit_ids(db_session, game_id: int, today: date) -> set:
    """
    Вклады под арестом: по ним есть неразобранная дуэль, где часть ставки цели взята с вклада.

    Дуэль, день разборки которой уже прошёл без розыгрыша, не разыграется (ставки сгорают
    по общему правилу), поэтому арест с вклада снимается.
    """
    rows = db_session.exec(
        select(CoinDuel.target_deposit_id, CoinDuel.year, CoinDuel.day).where(
            CoinDuel.game_id == game_id,
            CoinDuel.status == DUEL_STATUS_PENDING,
            CoinDuel.target_deposit_id.is_not(None),
            CoinDuel.target_deposit_part > 0,
        )
    ).all()
    today_key = (today.year, _day_of_year(today))
    return {deposit_id for deposit_id, year, day in rows if (year, day) >= today_key}


def is_deposit_arrested(db_session, deposit: CoinDeposit, today: date) -> bool:
    return deposit.id in get_arrested_deposit_ids(db_session, deposit.game_id, today)


def open_deposit(
    db_session,
    game_id: int,
    user_id: int,
    amount: int,
    term_days: int,
    today: date,
) -> Tuple[bool, str, Optional[CoinDeposit]]:
    """
    Открыть вклад: тело уходит из кошелька во вклад, проценты резервируются из банка чата.

    Returns:
        (success, reason, deposit). Коды ошибок: feature_disabled, not_registered,
        invalid_term, already_open, invalid_amount, insufficient_funds, bank_empty.
    """
    config = get_config_by_game_id(db_session, game_id)
    c = config.constants
    if not c.deposit_enabled:
        return False, "feature_disabled", None
    if term_days not in DEPOSIT_TERMS:
        return False, "invalid_term", None
    if not _is_active_player(db_session, game_id, user_id):
        return False, "not_registered", None

    # Сериализуем операции с вкладами и банком одного чата.
    db_session.exec(select(Game).where(Game.id == game_id).with_for_update()).first()

    if get_open_deposit(db_session, game_id, user_id) is not None:
        return False, "already_open", None

    rate_bp = rate_to_bp(get_key_rate())
    min_amount = calc_min_amount(rate_bp, term_days)
    if min_amount is None or amount < min_amount or amount > c.deposit_max_amount:
        return False, "invalid_amount", None
    interest = calc_interest(amount, rate_bp, term_days)
    if interest < 1:
        return False, "invalid_amount", None
    if amount > get_balance(db_session, game_id, user_id):
        return False, "insufficient_funds", None

    bank = get_or_create_chat_bank(db_session, game_id, auto_commit=False)
    if bank.balance < interest:
        return False, "bank_empty", None

    spend_coins(db_session, game_id, user_id, amount, today.year, "deposit_open", auto_commit=False)
    bank.balance -= interest
    bank.updated_at = datetime.utcnow()
    db_session.add(bank)
    deposit = CoinDeposit(
        game_id=game_id,
        user_id=user_id,
        amount=amount,
        initial_amount=amount,
        rate_bp=rate_bp,
        term_days=term_days,
        interest=interest,
        opened_date=today,
        matures_on=today + timedelta(days=term_days),
        status=DEPOSIT_STATUS_OPEN,
    )
    db_session.add(deposit)
    db_session.commit()
    db_session.refresh(deposit)
    logger.info(
        "Deposit opened: game=%s user=%s amount=%s term=%s rate_bp=%s interest=%s matures=%s",
        game_id, user_id, amount, term_days, rate_bp, interest, deposit.matures_on,
    )
    return True, "success", deposit


def _pay_out(db_session, deposit: CoinDeposit, pay_year: int, now: datetime) -> None:
    """Выплатить тело и зарезервированные проценты (без коммита)."""
    if deposit.amount > 0:
        add_coins(
            db_session, deposit.game_id, deposit.user_id, deposit.amount,
            pay_year, "deposit_return", auto_commit=False,
        )
    if deposit.interest > 0:
        add_coins(
            db_session, deposit.game_id, deposit.user_id, deposit.interest,
            pay_year, "deposit_interest", auto_commit=False,
        )
    deposit.paid_interest = deposit.interest
    deposit.status = DEPOSIT_STATUS_PAID
    deposit.closed_at = now
    db_session.add(deposit)


def settle_matured_deposits(
    db_session,
    game_id: int,
    today: date,
    auto_commit: bool = False,
) -> List[CoinDeposit]:
    """
    Закрыть все созревшие вклады чата (matures_on <= today): тело и проценты — в кошелёк
    транзакциями с годом выплаты.

    Работает независимо от флага deposit_enabled и от активности игрока. Вклады под
    арестом пропускаются до разборки дуэли. Повторный вызов ничего не начисляет: закрытые
    вклады имеют другой статус. По умолчанию без коммита — коммитит вызывающий розыгрыш.
    """
    due = list(db_session.exec(
        select(CoinDeposit).where(
            CoinDeposit.game_id == game_id,
            CoinDeposit.status == DEPOSIT_STATUS_OPEN,
            CoinDeposit.matures_on <= today,
        ).order_by(CoinDeposit.id).with_for_update()
    ).all())
    if not due:
        return []

    arrested = get_arrested_deposit_ids(db_session, game_id, today)
    now = datetime.utcnow()
    paid = []
    for deposit in due:
        if deposit.id in arrested:
            continue
        _pay_out(db_session, deposit, today.year, now)
        paid.append(deposit)
        logger.info(
            "Deposit %s paid: user=%s amount=%s interest=%s",
            deposit.id, deposit.user_id, deposit.amount, deposit.interest,
        )
    if paid and auto_commit:
        db_session.commit()
    return paid


def withdraw_deposit(
    db_session,
    game_id: int,
    user_id: int,
    today: date,
) -> Tuple[bool, str, Optional[CoinDeposit]]:
    """
    Снять вклад досрочно: тело возвращается полностью, проценты возвращаются в банк чата.

    Работает при выключенном флаге. Нельзя, пока вклад под арестом дуэли.
    Если срок уже вышел, вклад выплачивается как обычно (причина "matured").

    Returns:
        (success, reason, deposit). Коды: no_deposit, arrested, matured, success.
    """
    db_session.exec(select(Game).where(Game.id == game_id).with_for_update()).first()
    deposit = get_open_deposit(db_session, game_id, user_id)
    if deposit is None:
        return False, "no_deposit", None
    if is_deposit_arrested(db_session, deposit, today):
        return False, "arrested", deposit

    now = datetime.utcnow()
    if deposit.matures_on <= today:
        _pay_out(db_session, deposit, today.year, now)
        db_session.commit()
        return True, "matured", deposit

    if deposit.amount > 0:
        add_coins(
            db_session, game_id, user_id, deposit.amount, today.year, "deposit_return", auto_commit=False,
        )
    bank = get_or_create_chat_bank(db_session, game_id, auto_commit=False)
    bank.balance += deposit.interest
    bank.updated_at = now
    db_session.add(bank)
    deposit.status = DEPOSIT_STATUS_WITHDRAWN
    deposit.closed_at = now
    db_session.add(deposit)
    db_session.commit()
    logger.info(
        "Deposit %s withdrawn early: user=%s amount=%s interest_returned=%s",
        deposit.id, user_id, deposit.amount, deposit.interest,
    )
    return True, "success", deposit


def collect_deposit_part(
    db_session,
    deposit: CoinDeposit,
    part: int,
    pay_year: int,
    now: datetime,
) -> int:
    """
    Коллекторы: проигравшая цель дуэли теряет вклад досрочно. Недостача (part) уходит в банк
    дуэли, остаток тела возвращается в кошелёк, зарезервированные проценты — в банк чата.
    Без коммита. Возвращает фактически изъятую сумму (не больше тела вклада).
    """
    collected = min(max(part, 0), deposit.amount)
    rest = deposit.amount - collected
    if rest > 0:
        add_coins(
            db_session, deposit.game_id, deposit.user_id, rest, pay_year, "deposit_return", auto_commit=False,
        )
    bank = get_or_create_chat_bank(db_session, deposit.game_id, auto_commit=False)
    bank.balance += deposit.interest
    bank.updated_at = now
    db_session.add(bank)
    deposit.status = DEPOSIT_STATUS_COLLECTED
    deposit.closed_at = now
    db_session.add(deposit)
    logger.info(
        "Deposit %s collected: user=%s taken=%s returned=%s interest_to_bank=%s",
        deposit.id, deposit.user_id, collected, rest, deposit.interest,
    )
    return collected


def get_bank_deposit_totals(db_session, game_id: int) -> Tuple[int, int]:
    """(сумма тел открытых вкладов, сумма зарезервированных процентов) по чату."""
    rows = db_session.exec(
        select(CoinDeposit.amount, CoinDeposit.interest).where(
            CoinDeposit.game_id == game_id,
            CoinDeposit.status == DEPOSIT_STATUS_OPEN,
        )
    ).all()
    amount_total = 0
    interest_total = 0
    for amount, interest in rows:
        amount_total += amount
        interest_total += interest
    return amount_total, interest_total


def format_deposit_payouts_block(db_session, deposits: Iterable[CoinDeposit]) -> str:
    """Строки выплат по вкладам для сообщения /pidor (пусто, если выплат не было)."""
    deposits = list(deposits)
    if not deposits:
        return ""
    lines = [DEPOSIT_PAYOUT_HEADER]
    for deposit in deposits:
        user = db_session.get(TGUser, deposit.user_id)
        lines.append(DEPOSIT_PAYOUT_LINE.format(
            user=html_escape(user.full_username()) if user is not None else "?",
            amount=deposit.amount,
            interest=deposit.paid_interest,
        ))
    return "\n".join(lines)


def add_deposit_status(db_session, game_id: int, user_id: int, active_effects: dict) -> dict:
    """Добавить в active_effects магазина строку о вкладе игрока (если он открыт)."""
    from bot.handlers.game.shop_helpers import format_date_readable

    deposit = get_open_deposit(db_session, game_id, user_id)
    if deposit is not None:
        active_effects['deposit_amount'] = deposit.amount
        active_effects['deposit_matures'] = format_date_readable(
            deposit.matures_on.year, _day_of_year(deposit.matures_on)
        )
    return active_effects
