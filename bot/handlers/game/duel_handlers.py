"""Telegram handlers for «Раз на раз» (coin duel) and «Вызвать ментов» (police)."""
import logging
from datetime import date
from html import escape as html_escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from bot.app.models import TGUser
from bot.handlers.game.commands import current_datetime, ensure_game
from bot.handlers.game.config import get_config
from bot.handlers.game.duel_service import (
    calc_leverage,
    calc_target_stake,
    call_police,
    create_duel,
    format_leverage,
    get_challenger_duel_today,
    get_duel_target_day,
    get_duel_targets,
    get_police_call,
    get_stake_options,
    get_target_duel,
    get_year_balances,
)
from bot.handlers.game.membership_service import get_active_players
from bot.handlers.game.shop_helpers import format_date_readable
from bot.handlers.game.text_static import (
    ACHIEVEMENT_EARNED_NO_REWARD_TEMPLATE,
    ACHIEVEMENTS_EARNED_HEADER,
    DUEL_ANNOUNCEMENT,
    DUEL_ERROR_ALREADY_CHALLENGED,
    DUEL_ERROR_POLICE_ON_DUTY,
    DUEL_ERROR_TARGET_BUSY,
    DUEL_ERROR_TARGET_NOT_RICHER,
    DUEL_SELECT_STAKE,
    DUEL_SELECT_TARGET,
    POLICE_ANNOUNCEMENT,
    POLICE_ERROR_COOLDOWN,
    POLICE_SHOP_DESCRIPTION,
    POLICE_SHOP_NAME,
    SHOP_ERROR_NOT_YOUR_SHOP,
)
from bot.utils import ECallbackContext

logger = logging.getLogger(__name__)

DUEL_ERROR_DISABLED = "❌ Раз на раз отключён в этом чате"
DUEL_ERROR_NO_TARGETS = "❌ Богаче тебя тут никого нет"
DUEL_ERROR_GENERIC = "❌ Не получилось"


def duel_callback(owner_id: int) -> str:
    return f"shop_duel_{owner_id}"


def duel_target_callback(target_id: int, owner_id: int) -> str:
    return f"shop_duel_t_{target_id}_{owner_id}"


def duel_stake_callback(target_id: int, amount: int, owner_id: int) -> str:
    return f"shop_duel_x_{target_id}_{amount}_{owner_id}"


def police_callback(owner_id: int) -> str:
    return f"shop_police_{owner_id}"


def police_confirm_callback(owner_id: int) -> str:
    return f"shop_police_ok_{owner_id}"


def _int_parts(callback_data: str) -> list:
    return [int(part) for part in callback_data.split("_") if part.isdigit()]


def _back_button(owner_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ Назад в магазин", callback_data=f"shop_back_{owner_id}")


async def _reject_foreign_shop(query, owner_id: int) -> bool:
    if query.from_user.id == owner_id:
        return False
    await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
    return True


def _player_label(player: TGUser) -> str:
    label = player.first_name
    if player.last_name:
        label += f" {player.last_name}"
    return label


def _today(now) -> date:
    return now.date()


def _duel_error_text(reason: str, target: TGUser = None, min_stake: int = 2) -> str:
    target_name = target.full_username() if target is not None else "цели"
    messages = {
        "feature_disabled": DUEL_ERROR_DISABLED,
        "police_on_duty": DUEL_ERROR_POLICE_ON_DUTY,
        "already_challenged": DUEL_ERROR_ALREADY_CHALLENGED,
        "target_busy": DUEL_ERROR_TARGET_BUSY.format(target=target_name),
        "target_not_richer": DUEL_ERROR_TARGET_NOT_RICHER,
        "insufficient_funds": f"❌ Недостаточно койнов. Минимум {min_stake} 🪙.",
        "invalid_stake": DUEL_ERROR_GENERIC,
        "not_registered": "❌ Сначала зарегистрируйся: /pidoreg",
    }
    return messages.get(reason, DUEL_ERROR_GENERIC)


@ensure_game
async def handle_shop_duel_callback(update: Update, context: ECallbackContext):
    """Кнопка «Раз на раз»: выбор цели среди тех, кто богаче."""
    query = update.callback_query
    owner_id = _int_parts(query.data)[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    config = get_config(update.effective_chat.id)
    c = config.constants
    if not c.duel_enabled:
        await query.answer(DUEL_ERROR_DISABLED, show_alert=True)
        return

    db = context.db_session
    today = _today(current_datetime())
    fight_year, fight_day = get_duel_target_day(db, context.game.id, today, c.duel_same_day)
    if get_police_call(db, context.game.id, fight_year, fight_day) is not None:
        await query.answer(DUEL_ERROR_POLICE_ON_DUTY, show_alert=True)
        return
    if get_challenger_duel_today(db, context.game.id, context.tg_user.id, today) is not None:
        await query.answer(DUEL_ERROR_ALREADY_CHALLENGED, show_alert=True)
        return

    targets = get_duel_targets(
        db, context.game.id, context.tg_user.id, today.year,
        get_active_players(db, context.game.id),
    )
    if not targets:
        await query.answer(DUEL_ERROR_NO_TARGETS, show_alert=True)
        return

    buttons = [
        InlineKeyboardButton(
            f"{_player_label(player)} · {balance} 🪙",
            callback_data=duel_target_callback(player.id, owner_id),
        )
        for player, balance in targets
    ]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    rows.append([_back_button(owner_id)])
    await query.edit_message_text(
        html_escape(DUEL_SELECT_TARGET),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


@ensure_game
async def handle_shop_duel_target_callback(update: Update, context: ECallbackContext):
    """Выбрана цель: показать кнопки ставки и множитель."""
    query = update.callback_query
    parts = _int_parts(query.data)
    target_id, owner_id = parts[-2], parts[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    config = get_config(update.effective_chat.id)
    c = config.constants
    if not c.duel_enabled:
        await query.answer(DUEL_ERROR_DISABLED, show_alert=True)
        return

    db = context.db_session
    today = _today(current_datetime())
    target = db.get(TGUser, target_id)
    if target is None:
        await query.answer(DUEL_ERROR_GENERIC, show_alert=True)
        return
    fight_year, fight_day = get_duel_target_day(db, context.game.id, today, c.duel_same_day)
    if get_target_duel(db, context.game.id, target_id, fight_year, fight_day) is not None:
        await query.answer(_duel_error_text("target_busy", target), show_alert=True)
        return

    balances = get_year_balances(db, context.game.id, today.year, [context.tg_user.id, target_id])
    challenger_balance = balances.get(context.tg_user.id, 0)
    target_balance = balances.get(target_id, 0)
    if target_balance <= challenger_balance:
        await query.answer(DUEL_ERROR_TARGET_NOT_RICHER, show_alert=True)
        return

    stakes = get_stake_options(challenger_balance, c.transfer_min_amount, c.duel_max_stake)
    if not stakes:
        await query.answer(
            _duel_error_text("insufficient_funds", min_stake=c.transfer_min_amount),
            show_alert=True,
        )
        return

    k10 = calc_leverage(challenger_balance, target_balance, c.duel_max_leverage)
    buttons = [
        InlineKeyboardButton(
            f"{amount} против {calc_target_stake(amount, k10, target_balance)} 🪙",
            callback_data=duel_stake_callback(target_id, amount, owner_id),
        )
        for amount in stakes
    ]
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    rows.append([_back_button(owner_id)])
    await query.edit_message_text(
        html_escape(DUEL_SELECT_STAKE.format(target=target.full_username(), k=format_leverage(k10))),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    await query.answer()


@ensure_game
async def handle_shop_duel_stake_callback(update: Update, context: ECallbackContext):
    """Выбрана ставка: создать дуэль и объявить её в чате."""
    query = update.callback_query
    parts = _int_parts(query.data)
    target_id, amount, owner_id = parts[-3], parts[-2], parts[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    config = get_config(update.effective_chat.id)
    db = context.db_session
    target = db.get(TGUser, target_id)
    success, reason, duel = create_duel(
        db, context.game.id, context.tg_user.id, target_id, amount,
        _today(current_datetime()),
    )
    if not success:
        await query.answer(
            _duel_error_text(reason, target, config.constants.transfer_min_amount),
            show_alert=True,
        )
        return

    await query.edit_message_text(
        DUEL_ANNOUNCEMENT.format(
            challenger=html_escape(context.tg_user.full_username()),
            target=html_escape(target.full_username() if target is not None else "?"),
            x=duel.challenger_stake,
            kx=duel.target_stake,
        ),
        parse_mode="HTML",
    )
    await query.answer("🥊 Вызов брошен!")


@ensure_game
async def handle_shop_police_callback(update: Update, context: ECallbackContext):
    """Кнопка «Вызвать ментов»: экран подтверждения."""
    query = update.callback_query
    owner_id = _int_parts(query.data)[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    config = get_config(update.effective_chat.id)
    c = config.constants
    if not c.duel_enabled:
        await query.answer(DUEL_ERROR_DISABLED, show_alert=True)
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🚔 Позвонить за {c.police_price} 🪙",
            callback_data=police_confirm_callback(owner_id),
        )],
        [_back_button(owner_id)],
    ])
    await query.edit_message_text(
        f"<b>{html_escape(POLICE_SHOP_NAME)}</b>\n\n{html_escape(POLICE_SHOP_DESCRIPTION)}",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await query.answer()


@ensure_game
async def handle_shop_police_confirm_callback(update: Update, context: ECallbackContext):
    """Подтверждение звонка: отменить разборки и объявить звонившего."""
    query = update.callback_query
    owner_id = _int_parts(query.data)[-1]
    if await _reject_foreign_shop(query, owner_id):
        return
    config = get_config(update.effective_chat.id)
    c = config.constants
    success, reason, _duels, achievement = call_police(
        context.db_session, context.game.id, context.tg_user.id,
        _today(current_datetime()),
    )
    if not success:
        if reason.startswith("cooldown:"):
            cooldown_end = date.fromisoformat(reason.split(":", 1)[1])
            text = POLICE_ERROR_COOLDOWN.format(
                date=format_date_readable(cooldown_end.year, cooldown_end.timetuple().tm_yday)
            )
        else:
            messages = {
                "feature_disabled": DUEL_ERROR_DISABLED,
                "already_called": DUEL_ERROR_POLICE_ON_DUTY,
                "insufficient_funds": f"❌ Недостаточно койнов. Нужно {c.police_price} 🪙.",
                "not_registered": "❌ Сначала зарегистрируйся: /pidoreg",
            }
            text = messages.get(reason, DUEL_ERROR_GENERIC)
        await query.answer(text, show_alert=True)
        return

    caller_name = html_escape(context.tg_user.full_username())
    text = POLICE_ANNOUNCEMENT.format(caller=caller_name)
    if achievement is not None:
        from bot.handlers.game.achievement_constants import get_achievement
        achievement_data = get_achievement(achievement.achievement_code)
        if achievement_data:
            text += ACHIEVEMENTS_EARNED_HEADER + "\n" + ACHIEVEMENT_EARNED_NO_REWARD_TEMPLATE.format(
                username=caller_name,
                name=html_escape(achievement_data['name']),
            )
    await query.edit_message_text(text, parse_mode="HTML")
    await query.answer("🚔 Менты выехали!")
