"""Service functions for the totalizator (betting pool) feature."""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlmodel import select

from bot.app.models import Totalizator, TotalizatorBet, ChatBank, TGUser
from bot.handlers.game.cbr_service import calculate_commission_amount
from bot.handlers.game.coin_service import add_coins, get_balance
from bot.handlers.game.shop_service import spend_coins

logger = logging.getLogger(__name__)


def _get_or_create_chat_bank(db_session, game_id: int) -> ChatBank:
    stmt = select(ChatBank).where(ChatBank.game_id == game_id)
    bank = db_session.exec(stmt).first()
    if bank is None:
        bank = ChatBank(game_id=game_id, balance=0)
        db_session.add(bank)
        db_session.commit()
        db_session.refresh(bank)
    return bank


def create_totalizator(
    db_session,
    game_id: int,
    creator_id: int,
    title: str,
    stake: int,
    deadline_year: int,
    deadline_day: int,
) -> Totalizator:
    tot = Totalizator(
        game_id=game_id,
        creator_id=creator_id,
        title=title,
        stake=stake,
        deadline_year=deadline_year,
        deadline_day=deadline_day,
        status="open",
    )
    db_session.add(tot)
    db_session.commit()
    db_session.refresh(tot)
    logger.info(f"Created totalizator {tot.id} in game {game_id} by user {creator_id}")
    return tot


def get_open_totalizators(db_session, game_id: int) -> List[Totalizator]:
    stmt = select(Totalizator).where(
        Totalizator.game_id == game_id,
        Totalizator.status == "open",
    )
    return db_session.exec(stmt).all()


def get_expired_unresolved(db_session, game_id: int, current_year: int, current_day: int) -> List[Totalizator]:
    """Открытые тотализаторы, у которых дедлайн прошёл."""
    stmt = select(Totalizator).where(
        Totalizator.game_id == game_id,
        Totalizator.status == "open",
    )
    all_open = db_session.exec(stmt).all()
    expired = []
    for tot in all_open:
        if (tot.deadline_year, tot.deadline_day) < (current_year, current_day):
            expired.append(tot)
    return expired


def get_user_open_totalizators(db_session, game_id: int, user_id: int) -> List[Totalizator]:
    stmt = select(Totalizator).where(
        Totalizator.game_id == game_id,
        Totalizator.creator_id == user_id,
        Totalizator.status == "open",
    )
    return db_session.exec(stmt).all()


def get_totalizator_bets(db_session, totalizator_id: int) -> List[TotalizatorBet]:
    stmt = select(TotalizatorBet).where(TotalizatorBet.totalizator_id == totalizator_id)
    return db_session.exec(stmt).all()


def has_user_bet(db_session, totalizator_id: int, user_id: int) -> bool:
    stmt = select(TotalizatorBet).where(
        TotalizatorBet.totalizator_id == totalizator_id,
        TotalizatorBet.user_id == user_id,
    )
    return db_session.exec(stmt).first() is not None


def place_bet(
    db_session,
    totalizator: Totalizator,
    user_id: int,
    choice: str,
    year: int,
) -> TotalizatorBet:
    """
    Разместить ставку. Списывает stake с игрока, комиссию кладёт в банк.

    Комиссия берётся ИЗ ставки (вариант B):
      commission = calculate_commission_amount(stake)
      effective = stake - commission
    Игрок платит ровно stake. В пул попадает effective * N.
    """
    stake = totalizator.stake
    commission = calculate_commission_amount(stake)

    # Списываем ставку с игрока
    spend_coins(db_session, totalizator.game_id, user_id, stake, year,
                "totalizator_bet", auto_commit=False)

    # Комиссию в банк
    bank = _get_or_create_chat_bank(db_session, totalizator.game_id)
    bank.balance += commission
    db_session.add(bank)

    bet = TotalizatorBet(
        totalizator_id=totalizator.id,
        user_id=user_id,
        choice=choice,
    )
    db_session.add(bet)
    db_session.commit()
    db_session.refresh(bet)
    logger.info(
        f"Placed bet: user={user_id} tot={totalizator.id} choice={choice} "
        f"stake={stake} commission={commission}"
    )
    return bet


def resolve_totalizator(
    db_session,
    totalizator: Totalizator,
    winning_choice: str,  # "yes" | "no" | "cancel"
    year: int,
) -> dict:
    """
    Завершить тотализатор.

    winning_choice:
      "yes" / "no" — победившая сторона
      "cancel"     — отмена (вернуть ставки)

    Возвращает словарь:
      {
        "winners": [TotalizatorBet, ...],
        "losers": [TotalizatorBet, ...],
        "per_winner": int,
        "cancelled": bool,      # если winning_choice == "cancel"
        "refunded": bool,       # если все на одной стороне
        "effective": int,       # что каждый получает при отмене/рефанде
        "commission": int,      # комиссия с каждой ставки
      }
    """
    bets = get_totalizator_bets(db_session, totalizator.id)
    stake = totalizator.stake
    commission = calculate_commission_amount(stake)
    effective = stake - commission  # что идёт в пул от каждой ставки

    yes_bets = [b for b in bets if b.choice == "yes"]
    no_bets = [b for b in bets if b.choice == "no"]

    cancelled = winning_choice == "cancel"
    all_one_side = (bool(yes_bets) != bool(no_bets)) and bool(bets)  # все на одной стороне
    refunded = (not cancelled) and all_one_side

    if cancelled or refunded:
        # Вернуть effective каждому ставившему
        for bet in bets:
            add_coins(db_session, totalizator.game_id, bet.user_id, effective, year,
                      "totalizator_refund", auto_commit=False)
        new_status = "cancelled" if cancelled else ("resolved_yes" if yes_bets else "resolved_no")
        totalizator.status = new_status
        totalizator.resolved_at = datetime.utcnow()
        db_session.add(totalizator)
        db_session.commit()
        return {
            "winners": [],
            "losers": bets,
            "per_winner": 0,
            "cancelled": cancelled,
            "refunded": refunded,
            "effective": effective,
            "commission": commission,
        }

    # Нормальный исход
    winners = yes_bets if winning_choice == "yes" else no_bets
    losers = no_bets if winning_choice == "yes" else yes_bets

    total_effective = effective * len(bets)
    per_winner = total_effective // len(winners) if winners else 0
    remainder = total_effective % len(winners) if winners else 0

    # Раздать победителям
    for bet in winners:
        add_coins(db_session, totalizator.game_id, bet.user_id, per_winner, year,
                  "totalizator_win", auto_commit=False)

    # Остаток в банк
    if remainder > 0:
        bank = _get_or_create_chat_bank(db_session, totalizator.game_id)
        bank.balance += remainder
        db_session.add(bank)

    totalizator.status = "resolved_yes" if winning_choice == "yes" else "resolved_no"
    totalizator.resolved_at = datetime.utcnow()
    db_session.add(totalizator)
    db_session.commit()

    logger.info(
        f"Resolved totalizator {totalizator.id}: choice={winning_choice} "
        f"winners={len(winners)} per_winner={per_winner} remainder={remainder}"
    )
    return {
        "winners": winners,
        "losers": losers,
        "per_winner": per_winner,
        "cancelled": False,
        "refunded": False,
        "effective": effective,
        "commission": commission,
    }


def format_totalizator_message(
    totalizator: Totalizator,
    bets: List[TotalizatorBet],
    db_session,
    with_mentions: bool = True,
) -> str:
    """Форматировать сообщение тотализатора с текущими ставками."""
    from bot.handlers.game.shop_helpers import format_date_readable

    yes_bets = [b for b in bets if b.choice == "yes"]
    no_bets = [b for b in bets if b.choice == "no"]

    def _names(bet_list):
        names = []
        for bet in bet_list:
            stmt = select(TGUser).where(TGUser.id == bet.user_id)
            user = db_session.exec(stmt).first()
            if user:
                names.append(user.full_username())
        return names

    yes_names = _names(yes_bets)
    no_names = _names(no_bets)

    stmt = select(TGUser).where(TGUser.id == totalizator.creator_id)
    creator = db_session.exec(stmt).first()
    creator_name = creator.full_username() if creator else "?"

    deadline_str = format_date_readable(totalizator.deadline_year, totalizator.deadline_day)

    yes_list = ", ".join(yes_names) if yes_names else "—"
    no_list = ", ".join(no_names) if no_names else "—"

    return (
        f"🎲 <b>Тотализатор от {creator_name}</b>\n\n"
        f"{totalizator.title}\n\n"
        f"⚖️ Ставка: <b>{totalizator.stake}</b> 🪙\n"
        f"📅 Дедлайн: {deadline_str}\n\n"
        f"👍 <b>{totalizator.option_yes}</b> ({len(yes_bets)}):\n{yes_list}\n\n"
        f"👎 <b>{totalizator.option_no}</b> ({len(no_bets)}):\n{no_list}"
    )
