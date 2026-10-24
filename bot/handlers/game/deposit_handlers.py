"""Telegram handlers for coin deposits («Вклад» в /pidorshop)."""
import logging
from datetime import date
from html import escape as html_escape
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from bot.app.models import CoinDeposit
from bot.handlers.game.cbr_service import get_key_rate
from bot.handlers.game.coin_service import get_balance
from bot.handlers.game.commands import current_datetime, ensure_game
from bot.handlers.game.config import get_config
from bot.handlers.game.deposit_service import (
    DEPOSIT_TERMS,
    calc_interest,
    calc_min_amount,
    format_rate,
    format_term_percent,
    get_amount_options,
    get_open_deposit,
    is_deposit_arrested,
    open_deposit,
    rate_to_bp,
    settle_matured_deposits,
    withdraw_deposit,
)
from bot.handlers.game.shop_helpers import format_date_readable
from bot.handlers.game.text_static import (
    DEPOSIT_AMOUNT_BUTTON,
    DEPOSIT_ERROR_ALREADY_OPEN,
    DEPOSIT_ERROR_AMOUNT,
    DEPOSIT_ERROR_ARRESTED,
    DEPOSIT_ERROR_BANK_EMPTY,
    DEPOSIT_ERROR_DISABLED,
    DEPOSIT_ERROR_GENERIC,
    DEPOSIT_ERROR_INSUFFICIENT,
    DEPOSIT_ERROR_NO_DEPOSIT,
    DEPOSIT_ERROR_RATE_TOO_LOW,
    DEPOSIT_INTRO,
    DEPOSIT_OPENED,
    DEPOSIT_PAID_ON_WITHDRAW,
    DEPOSIT_SELECT_AMOUNT,
    DEPOSIT_TERM_BUTTON,
    DEPOSIT_VIEW,
    DEPOSIT_VIEW_ARRESTED,
    DEPOSIT_WITHDRAW_BUTTON,
    DEPOSIT_WITHDRAW_CONFIRM,
    DEPOSIT_WITHDRAW_CONFIRM_BUTTON,
    DEPOSIT_WITHDRAWN,
    SHOP_ERROR_NOT_YOUR_SHOP,
)
from bot.handlers.game.transfer_service import get_or_create_chat_bank
from bot.utils import ECallbackContext

logger = logging.getLogger(__name__)


def deposit_callback(owner_id: int) -> str:
    return f"shop_deposit_{owner_id}"


def deposit_term_callback(term_days: int, owner_id: int) -> str:
    return f"shop_deposit_t_{term_days}_{owner_id}"


def deposit_open_callback(term_days: int, amount: int, owner_id: int) -> str:
    return f"shop_deposit_x_{term_days}_{amount}_{owner_id}"


def deposit_withdraw_callback(owner_id: int) -> str:
    return f"shop_deposit_w_{owner_id}"


def deposit_withdraw_confirm_callback(owner_id: int) -> str:
    return f"shop_deposit_w_ok_{owner_id}"


def _int_parts(callback_data: str) -> list:
    return [int(part) for part in callback_data.split("_") if part.isdigit()]


def _back_button(owner_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ Назад в магазин", callback_data=f"shop_back_{owner_id}")


async def _reject_foreign_shop(query, owner_id: int) -> bool:
    if query.from_user.id == owner_id:
        return False
    await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
    return True


def _today(now) -> date:
    return now.date()


def _readable(value: date) -> str:
    return format_date_readable(value.year, value.timetuple().tm_yday)


def _open_error_text(reason: str, min_amount: Optional[int] = None) -> str:
    messages = {
        "feature_disabled": DEPOSIT_ERROR_DISABLED,
        "not_registered": "❌ Сначала зарегистрируйся: /pidoreg",
        "already_open": DEPOSIT_ERROR_ALREADY_OPEN,
        "bank_empty": DEPOSIT_ERROR_BANK_EMPTY,
        "insufficient_funds": DEPOSIT_ERROR_INSUFFICIENT.format(min_amount=min_amount or 1),
        "rate_too_low": DEPOSIT_ERROR_RATE_TOO_LOW,
        "invalid_amount": DEPOSIT_ERROR_AMOUNT,
    }
    return messages.get(reason, DEPOSIT_ERROR_GENERIC)


def build_deposit_view(db, deposit: CoinDeposit, today: date, owner_id: int):
    """Экран открытого вклада: (текст HTML, клавиатура)."""
    text = DEPOSIT_VIEW.format(
        amount=deposit.amount,
        term=deposit.term_days,
        opened=html_escape(_readable(deposit.opened_date)),
        matures=html_escape(_readable(deposit.matures_on)),
        interest=deposit.interest,
    )
    rows = []
    if is_deposit_arrested(db, deposit, today):
        text += DEPOSIT_VIEW_ARRESTED
    else:
        rows.append([InlineKeyboardButton(
            DEPOSIT_WITHDRAW_BUTTON, callback_data=deposit_withdraw_callback(owner_id),
        )])
    rows.append([_back_button(owner_id)])
    return text, InlineKeyboardMarkup(rows)


@ensure_game
async def handle_shop_deposit_callback(update: Update, context: ECallbackContext):
    """Кнопка «Вклад»: выбор срока или экран открытого вклада."""
    query = update.callback_query
    owner_id = _int_parts(query.data)[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    c = get_config(update.effective_chat.id).constants
    db = context.db_session
    today = _today(current_datetime())

    settle_matured_deposits(db, context.game.id, today, auto_commit=True)
    deposit = get_open_deposit(db, context.game.id, context.tg_user.id)
    if deposit is not None:
        text, keyboard = build_deposit_view(db, deposit, today, owner_id)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
        await query.answer()
        return
    if not c.deposit_enabled:
        await query.answer(DEPOSIT_ERROR_DISABLED, show_alert=True)
        return

    rate_bp = rate_to_bp(get_key_rate())
    buttons = [
        InlineKeyboardButton(
            DEPOSIT_TERM_BUTTON.format(term=term, percent=format_term_percent(rate_bp, term)),
            callback_data=deposit_term_callback(term, owner_id),
        )
        for term in DEPOSIT_TERMS
    ]
    await query.edit_message_text(
        DEPOSIT_INTRO.format(rate=html_escape(format_rate(rate_bp)), max_amount=c.deposit_max_amount),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([buttons, [_back_button(owner_id)]]),
    )
    await query.answer()


@ensure_game
async def handle_shop_deposit_term_callback(update: Update, context: ECallbackContext):
    """Выбран срок: суммы, проценты по которым покрывает банк чата."""
    query = update.callback_query
    parts = _int_parts(query.data)
    term, owner_id = parts[-2], parts[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    c = get_config(update.effective_chat.id).constants
    if not c.deposit_enabled:
        await query.answer(DEPOSIT_ERROR_DISABLED, show_alert=True)
        return
    if term not in DEPOSIT_TERMS:
        await query.answer(DEPOSIT_ERROR_GENERIC, show_alert=True)
        return

    db = context.db_session
    if get_open_deposit(db, context.game.id, context.tg_user.id) is not None:
        await query.answer(DEPOSIT_ERROR_ALREADY_OPEN, show_alert=True)
        return

    rate_bp = rate_to_bp(get_key_rate())
    wallet = get_balance(db, context.game.id, context.tg_user.id)
    bank = get_or_create_chat_bank(db, context.game.id)
    options, reason = get_amount_options(rate_bp, term, c.deposit_max_amount, wallet, bank.balance)
    if not options:
        await query.answer(
            _open_error_text(reason, calc_min_amount(rate_bp, term)), show_alert=True,
        )
        return

    buttons = [
        InlineKeyboardButton(
            DEPOSIT_AMOUNT_BUTTON.format(amount=amount, interest=calc_interest(amount, rate_bp, term)),
            callback_data=deposit_open_callback(term, amount, owner_id),
        )
        for amount in options
    ]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    rows.append([_back_button(owner_id)])
    await query.edit_message_text(
        DEPOSIT_SELECT_AMOUNT.format(
            term=term,
            percent=format_term_percent(rate_bp, term),
            min_amount=options[0],
            wallet=wallet,
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


@ensure_game
async def handle_shop_deposit_open_callback(update: Update, context: ECallbackContext):
    """Выбрана сумма: открыть вклад."""
    query = update.callback_query
    parts = _int_parts(query.data)
    term, amount, owner_id = parts[-3], parts[-2], parts[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    success, reason, deposit = open_deposit(
        context.db_session, context.game.id, context.tg_user.id, amount, term,
        _today(current_datetime()),
    )
    if not success:
        await query.answer(_open_error_text(reason), show_alert=True)
        return

    await query.edit_message_text(
        DEPOSIT_OPENED.format(
            amount=deposit.amount,
            term=deposit.term_days,
            percent=format_term_percent(deposit.rate_bp, deposit.term_days),
            matures=html_escape(_readable(deposit.matures_on)),
            interest=deposit.interest,
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[_back_button(owner_id)]]),
    )
    await query.answer("💼 Вклад открыт!")


@ensure_game
async def handle_shop_deposit_withdraw_callback(update: Update, context: ECallbackContext):
    """Кнопка «Снять досрочно»: экран подтверждения."""
    query = update.callback_query
    owner_id = _int_parts(query.data)[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    db = context.db_session
    today = _today(current_datetime())
    deposit = get_open_deposit(db, context.game.id, context.tg_user.id)
    if deposit is None:
        await query.answer(DEPOSIT_ERROR_NO_DEPOSIT, show_alert=True)
        return
    if is_deposit_arrested(db, deposit, today):
        await query.answer(DEPOSIT_ERROR_ARRESTED, show_alert=True)
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            DEPOSIT_WITHDRAW_CONFIRM_BUTTON, callback_data=deposit_withdraw_confirm_callback(owner_id),
        )],
        [_back_button(owner_id)],
    ])
    await query.edit_message_text(
        DEPOSIT_WITHDRAW_CONFIRM.format(amount=deposit.amount, interest=deposit.interest),
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await query.answer()


@ensure_game
async def handle_shop_deposit_withdraw_confirm_callback(update: Update, context: ECallbackContext):
    """Подтверждение: вернуть тело вклада, проценты возвращаются в банк чата."""
    query = update.callback_query
    owner_id = _int_parts(query.data)[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    success, reason, deposit = withdraw_deposit(
        context.db_session, context.game.id, context.tg_user.id, _today(current_datetime()),
    )
    if not success:
        text = DEPOSIT_ERROR_ARRESTED if reason == "arrested" else DEPOSIT_ERROR_NO_DEPOSIT
        await query.answer(text, show_alert=True)
        return

    if reason == "matured":
        text = DEPOSIT_PAID_ON_WITHDRAW.format(amount=deposit.amount, interest=deposit.paid_interest)
    else:
        text = DEPOSIT_WITHDRAWN.format(amount=deposit.amount)
    await query.edit_message_text(
        text, reply_markup=InlineKeyboardMarkup([[_back_button(owner_id)]]),
    )
    await query.answer()
