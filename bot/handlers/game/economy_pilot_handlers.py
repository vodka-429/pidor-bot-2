"""Telegram handlers for the pilot economy features."""
import json
import logging
from html import escape as html_escape

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

from bot.app.models import KVItem
from bot.handlers.game.commands import (
    current_datetime,
    ensure_game,
    handle_totalizator_creation_text,
)
from bot.handlers.game.config import get_config
from bot.handlers.game.economy_pilot_service import (
    CUSTOM_PHRASE_MAX_LENGTH,
    TELEGRAM_TITLE_MAX_LENGTH,
    buy_custom_victory_phrase,
    clear_custom_victory_phrase,
    clear_recorded_telegram_title,
    execute_coin_rain,
    get_game_player,
    record_telegram_title_purchase,
    render_custom_victory_phrase,
    validate_custom_phrase,
    validate_telegram_title,
)
from bot.handlers.game.membership_service import get_active_players
from bot.handlers.game.shop_service import can_afford
from bot.handlers.game.text_static import SHOP_ERROR_NOT_YOUR_SHOP
from bot.utils import ECallbackContext, format_number


logger = logging.getLogger(__name__)


def _owner_id(callback_data: str) -> int:
    return int(callback_data.rsplit("_", 1)[1])


def _is_owner(query, owner_id: int) -> bool:
    return query.from_user.id == owner_id


def _draft_key(tg_user_id: int) -> str:
    return f"shop_draft_{tg_user_id}"


def _get_draft(context, chat_id: int, for_update: bool = False):
    query = context.db_session.query(KVItem).filter_by(
        chat_id=chat_id,
        key=_draft_key(context.tg_user.tg_id),
    )
    if for_update:
        query = query.with_for_update()
    return query.one_or_none()


def _save_draft(context, chat_id: int, payload: dict) -> None:
    draft = _get_draft(context, chat_id)
    value = json.dumps(payload, ensure_ascii=False)
    if draft is None:
        draft = KVItem(
            chat_id=chat_id,
            key=_draft_key(context.tg_user.tg_id),
            value=value,
        )
    else:
        draft.value = value
    context.db_session.add(draft)
    context.db_session.commit()


def _delete_draft(context, chat_id: int, auto_commit: bool = True) -> None:
    draft = _get_draft(context, chat_id)
    if draft is not None:
        context.db_session.delete(draft)
        if auto_commit:
            context.db_session.commit()


def _back_button(owner_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ Назад в магазин", callback_data=f"shop_back_{owner_id}")


async def _reject_foreign_shop(query, owner_id: int) -> bool:
    if _is_owner(query, owner_id):
        return False
    await query.answer(SHOP_ERROR_NOT_YOUR_SHOP, show_alert=True)
    return True


@ensure_game
async def handle_shop_rain_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    config = get_config(update.effective_chat.id)
    if not config.constants.coin_rain_enabled:
        await query.answer("❌ Койновый дождь отключён в этом чате", show_alert=True)
        return
    c = config.constants
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"🌧 Запустить за {c.coin_rain_price} 🪙",
            callback_data=f"shop_rain_confirm_{owner_id}",
        )],
        [_back_button(owner_id)],
    ])
    await query.edit_message_text(
        "🌧 <b>Койновый дождь</b>\n\n"
        f"До {c.coin_rain_max_recipients} случайных участников, кроме вас, получат "
        f"по {c.coin_rain_recipient_amount} 🪙. Весь остаток из {c.coin_rain_price} 🪙 "
        "уйдёт в банк чата.\n\n"
        "Лимиты: один дождь от пользователя и три дождя на чат в сутки.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await query.answer()


@ensure_game
async def handle_shop_rain_confirm_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    now = current_datetime()
    success, reason, recipients, bank_amount = execute_coin_rain(
        context.db_session,
        context.game.id,
        context.tg_user.id,
        get_active_players(context.db_session, context.game.id),
        now.year,
        now.timetuple().tm_yday,
    )
    if not success:
        config = get_config(update.effective_chat.id)
        messages = {
            "feature_disabled": "❌ Койновый дождь отключён в этом чате.",
            "buyer_daily_limit": "❌ Вы уже запускали койновый дождь сегодня.",
            "chat_daily_limit": "❌ Сегодня в этом чате уже было три койновых дождя.",
            "insufficient_funds": (
                f"❌ Недостаточно койнов. Нужно {config.constants.coin_rain_price} 🪙."
            ),
        }
        await query.answer(messages.get(reason, "❌ Не удалось запустить дождь"), show_alert=True)
        return

    reward = get_config(update.effective_chat.id).constants.coin_rain_recipient_amount
    if recipients:
        recipient_lines = "\n".join(
            f"• {html_escape(player.full_username())}: +{reward} 🪙"
            for player in recipients
        )
    else:
        recipient_lines = "• Подходящих участников нет"
    await query.edit_message_text(
        "🌧 <b>Койновый дождь прошёл!</b>\n\n"
        f"{recipient_lines}\n\n"
        f"🏦 В банк чата: {bank_amount} 🪙",
        parse_mode="HTML",
    )
    await query.answer("🌧 Дождь запущен!", show_alert=True)


@ensure_game
async def handle_shop_phrase_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    config = get_config(update.effective_chat.id)
    if not config.constants.custom_phrase_enabled:
        await query.answer("❌ Победные фразы отключены в этом чате", show_alert=True)
        return
    link = get_game_player(context.db_session, context.game.id, context.tg_user.id)
    current = "не задана"
    if link and link.custom_victory_phrase:
        current = render_custom_victory_phrase(
            context.tg_user,
            link.custom_victory_phrase,
            link.custom_victory_name_position or "start",
        )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Имя в начале", callback_data=f"shop_phrase_start_{owner_id}"),
            InlineKeyboardButton("Имя в конце", callback_data=f"shop_phrase_end_{owner_id}"),
        ],
        [InlineKeyboardButton("🧹 Удалить бесплатно", callback_data=f"shop_phrase_clear_{owner_id}")],
        [_back_button(owner_id)],
    ])
    await query.edit_message_text(
        "✍️ <b>Личная победная фраза</b>\n\n"
        f"Текущая: {current}\n\n"
        f"Новое или изменённое сообщение стоит {config.constants.custom_phrase_price} 🪙. "
        "Удаление бесплатно. Выберите положение имени:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await query.answer()


@ensure_game
async def handle_shop_phrase_position_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    position = "start" if "_start_" in query.data else "end"
    _save_draft(context, update.effective_chat.id, {
        "kind": "victory_phrase_input",
        "position": position,
    })
    await query.edit_message_text(
        "✍️ Пришлите победную фразу одним сообщением.\n\n"
        f"Одна строка, не больше {CUSTOM_PHRASE_MAX_LENGTH} символов. "
        "Перед списанием койнов бот покажет предпросмотр."
    )
    await query.answer()


@ensure_game
async def handle_shop_phrase_confirm_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    # The row lock makes repeated/concurrent presses of the same purchase
    # button idempotent: only the first request can consume the draft.
    draft = _get_draft(context, update.effective_chat.id, for_update=True)
    if draft is None:
        await query.answer("❌ Черновик устарел, начните заново", show_alert=True)
        return
    payload = json.loads(draft.value)
    if payload.get("kind") != "victory_phrase_confirm":
        await query.answer("❌ Черновик устарел, начните заново", show_alert=True)
        return
    success, reason, commission = buy_custom_victory_phrase(
        context.db_session,
        context.game.id,
        context.tg_user.id,
        payload["phrase"],
        payload["position"],
        current_datetime().year,
        auto_commit=False,
    )
    if not success:
        message = "❌ Недостаточно койнов" if reason == "insufficient_funds" else "❌ Не удалось сохранить фразу"
        await query.answer(message, show_alert=True)
        return
    _delete_draft(context, update.effective_chat.id, auto_commit=False)
    context.db_session.commit()
    await query.edit_message_text(
        "✅ <b>Победная фраза сохранена</b>\n\n"
        f"Комиссия в банк: {commission} 🪙",
        parse_mode="HTML",
    )
    await query.answer("✅ Фраза сохранена", show_alert=True)


@ensure_game
async def handle_shop_phrase_clear_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    clear_custom_victory_phrase(context.db_session, context.game.id, context.tg_user.id)
    _delete_draft(context, update.effective_chat.id)
    await query.edit_message_text("✅ Победная фраза удалена. Койны не списывались.")
    await query.answer()


@ensure_game
async def handle_shop_title_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    config = get_config(update.effective_chat.id)
    if not config.constants.telegram_title_enabled:
        await query.answer("❌ Telegram-титулы отключены в этом чате", show_alert=True)
        return
    link = get_game_player(context.db_session, context.game.id, context.tg_user.id)
    current = html_escape(link.telegram_title) if link and link.telegram_title else "не задан"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Ввести титул", callback_data=f"shop_title_input_{owner_id}")],
        [InlineKeyboardButton("🧹 Удалить бесплатно", callback_data=f"shop_title_clear_{owner_id}")],
        [_back_button(owner_id)],
    ])
    await query.edit_message_text(
        "🏷 <b>Telegram-титул — тестовый режим</b>\n\n"
        f"Сохранённый титул: {current}\n"
        f"Цена установки или замены: {config.constants.telegram_title_price} 🪙. "
        "Удаление бесплатно.\n\n"
        "У владельца чата и некоторых администраторов бот не может изменить титул сам: "
        "в этом случае он попросит сделать это вручную и проверит результат.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await query.answer()


@ensure_game
async def handle_shop_title_input_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    _save_draft(context, update.effective_chat.id, {"kind": "telegram_title_input"})
    await query.edit_message_text(
        "🏷 Пришлите новый титул одним сообщением.\n\n"
        f"Не больше {TELEGRAM_TITLE_MAX_LENGTH} символов, без emoji и переносов строки. "
        "Перед списанием койнов бот покажет предпросмотр."
    )
    await query.answer()


async def _apply_title(context, chat_id: int, member, title: str) -> tuple[str, str]:
    """Return (mode, previous value). mode is admin or member."""
    if member.status == ChatMemberStatus.ADMINISTRATOR:
        previous = getattr(member, "custom_title", None) or ""
        await context.bot.set_chat_administrator_custom_title(
            chat_id=chat_id,
            user_id=context.tg_user.tg_id,
            custom_title=title,
        )
        return "admin", previous

    bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
    if not getattr(bot_member, "can_manage_tags", False):
        raise PermissionError("bot_cannot_manage_tags")
    previous = getattr(member, "tag", None) or ""
    await context.bot.set_chat_member_tag(
        chat_id=chat_id,
        user_id=context.tg_user.tg_id,
        tag=title,
    )
    return "member", previous


async def _restore_title(context, chat_id: int, mode: str, previous: str) -> None:
    try:
        if mode == "admin":
            await context.bot.set_chat_administrator_custom_title(
                chat_id=chat_id,
                user_id=context.tg_user.tg_id,
                custom_title=previous,
            )
        else:
            await context.bot.set_chat_member_tag(
                chat_id=chat_id,
                user_id=context.tg_user.tg_id,
                tag=previous,
            )
    except TelegramError:
        logger.exception("Failed to restore Telegram title after database failure")


def _manual_title_required(member) -> bool:
    return (
        member.status == ChatMemberStatus.OWNER
        or (
            member.status == ChatMemberStatus.ADMINISTRATOR
            and not getattr(member, "can_be_edited", False)
        )
    )


async def _show_manual_title_verification(query, context, title: str, clear: bool = False) -> None:
    _save_draft(context, query.message.chat.id, {
        "kind": "telegram_title_verify",
        "title": title,
        "clear": clear,
    })
    owner_id = query.from_user.id
    action = "удалите текущий титул" if clear else f"поставьте титул «{html_escape(title)}»"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Проверить", callback_data=f"shop_title_verify_{owner_id}")],
        [_back_button(owner_id)],
    ])
    await query.edit_message_text(
        "🏷 <b>Нужна ручная установка</b>\n\n"
        f"В настройках администратора {action}, затем нажмите «Проверить».\n\n"
        "Койны будут списаны только после точного совпадения.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@ensure_game
async def handle_shop_title_confirm_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    # Keep the draft locked across the Telegram API call and the coin charge.
    draft = _get_draft(context, update.effective_chat.id, for_update=True)
    if draft is None:
        await query.answer("❌ Черновик устарел, начните заново", show_alert=True)
        return
    payload = json.loads(draft.value)
    if payload.get("kind") != "telegram_title_confirm":
        await query.answer("❌ Черновик устарел, начните заново", show_alert=True)
        return
    title = payload["title"]
    config = get_config(update.effective_chat.id)
    if not can_afford(
        context.db_session, context.game.id, context.tg_user.id,
        config.constants.telegram_title_price,
    ):
        await query.answer("❌ Недостаточно койнов", show_alert=True)
        return

    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, context.tg_user.tg_id)
        if _manual_title_required(member):
            await _show_manual_title_verification(query, context, title)
            await query.answer("Установите титул вручную")
            return
        mode, previous = await _apply_title(context, update.effective_chat.id, member, title)
    except PermissionError:
        await query.answer("❌ У бота нет права управлять тегами участников", show_alert=True)
        return
    except TelegramError as error:
        logger.warning("Telegram rejected title change: %s", error)
        await query.answer("❌ Telegram не разрешил изменить титул", show_alert=True)
        return

    try:
        success, reason, commission = record_telegram_title_purchase(
            context.db_session,
            context.game.id,
            context.tg_user.id,
            title,
            current_datetime().year,
            auto_commit=False,
        )
        if not success:
            await _restore_title(context, update.effective_chat.id, mode, previous)
            await query.answer("❌ Не удалось списать койны", show_alert=True)
            return
        _delete_draft(context, update.effective_chat.id, auto_commit=False)
        context.db_session.commit()
    except Exception:
        context.db_session.rollback()
        await _restore_title(context, update.effective_chat.id, mode, previous)
        raise
    await query.edit_message_text(
        "✅ <b>Telegram-титул установлен</b>\n\n"
        f"Комиссия в банк: {commission} 🪙",
        parse_mode="HTML",
    )
    await query.answer("✅ Титул установлен", show_alert=True)


@ensure_game
async def handle_shop_title_verify_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    draft = _get_draft(context, update.effective_chat.id, for_update=True)
    if draft is None:
        await query.answer("❌ Проверка устарела, начните заново", show_alert=True)
        return
    payload = json.loads(draft.value)
    if payload.get("kind") != "telegram_title_verify":
        await query.answer("❌ Проверка устарела, начните заново", show_alert=True)
        return
    desired = payload.get("title", "")
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, context.tg_user.tg_id)
    except TelegramError:
        await query.answer("❌ Не удалось проверить титул через Telegram", show_alert=True)
        return
    actual = getattr(member, "custom_title", None) or ""
    if actual != desired:
        await query.answer(
            "❌ Титул пока не совпадает" if desired else "❌ Титул ещё не удалён",
            show_alert=True,
        )
        return

    if payload.get("clear"):
        clear_recorded_telegram_title(
            context.db_session,
            context.game.id,
            context.tg_user.id,
            auto_commit=False,
        )
        commission = None
    else:
        success, reason, commission = record_telegram_title_purchase(
            context.db_session,
            context.game.id,
            context.tg_user.id,
            desired,
            current_datetime().year,
            auto_commit=False,
        )
        if not success:
            message = "❌ Недостаточно койнов" if reason == "insufficient_funds" else "❌ Не удалось сохранить покупку"
            await query.answer(message, show_alert=True)
            return
    _delete_draft(context, update.effective_chat.id, auto_commit=False)
    context.db_session.commit()
    suffix = "Койны не списывались." if commission is None else f"Комиссия в банк: {commission} 🪙"
    await query.edit_message_text(
        f"✅ <b>Telegram-титул {'удалён' if payload.get('clear') else 'подтверждён'}</b>\n\n{suffix}",
        parse_mode="HTML",
    )
    await query.answer("✅ Проверка пройдена", show_alert=True)


@ensure_game
async def handle_shop_title_clear_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, context.tg_user.tg_id)
        if _manual_title_required(member):
            await _show_manual_title_verification(query, context, "", clear=True)
            await query.answer("Удалите титул вручную")
            return
        mode, previous = await _apply_title(context, update.effective_chat.id, member, "")
    except PermissionError:
        await query.answer("❌ У бота нет права управлять тегами участников", show_alert=True)
        return
    except TelegramError as error:
        logger.warning("Telegram rejected title clear: %s", error)
        await query.answer("❌ Telegram не разрешил удалить титул", show_alert=True)
        return
    try:
        clear_recorded_telegram_title(
            context.db_session,
            context.game.id,
            context.tg_user.id,
            auto_commit=False,
        )
        _delete_draft(context, update.effective_chat.id, auto_commit=False)
        context.db_session.commit()
    except Exception:
        context.db_session.rollback()
        await _restore_title(context, update.effective_chat.id, mode, previous)
        raise
    await query.edit_message_text("✅ Telegram-титул удалён. Койны не списывались.")
    await query.answer()


@ensure_game
async def handle_shop_text_input(update: Update, context: ECallbackContext):
    """Single text dispatcher for shop drafts and the existing totalizator draft."""
    if update.message is None or update.message.text is None:
        return
    draft = _get_draft(context, update.effective_chat.id)
    if draft is None:
        await handle_totalizator_creation_text.__wrapped__(update, context)
        return
    try:
        payload = json.loads(draft.value)
    except (TypeError, json.JSONDecodeError):
        _delete_draft(context, update.effective_chat.id)
        await update.message.reply_text("❌ Черновик повреждён. Откройте /pidorshop и начните заново.")
        return

    kind = payload.get("kind")
    if kind == "victory_phrase_input":
        try:
            phrase = validate_custom_phrase(update.message.text)
        except ValueError as error:
            messages = {
                "empty": "❌ Фраза не может быть пустой.",
                "multiline": "❌ Фраза должна помещаться в одну строку.",
                "too_long": f"❌ Максимум {CUSTOM_PHRASE_MAX_LENGTH} символов.",
            }
            await update.message.reply_text(messages.get(str(error), "❌ Некорректная фраза."))
            return
        payload.update(kind="victory_phrase_confirm", phrase=phrase)
        _save_draft(context, update.effective_chat.id, payload)
        preview = render_custom_victory_phrase(context.tg_user, phrase, payload["position"])
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Купить", callback_data=f"shop_phrase_confirm_{context.tg_user.tg_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"shop_phrase_clear_draft_{context.tg_user.tg_id}"),
        ]])
        await update.message.reply_text(
            f"✍️ <b>Предпросмотр</b>\n\n{preview}",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    if kind == "telegram_title_input":
        try:
            title = validate_telegram_title(update.message.text)
        except ValueError as error:
            messages = {
                "empty": "❌ Титул не может быть пустым.",
                "multiline": "❌ Титул должен помещаться в одну строку.",
                "too_long": f"❌ Максимум {TELEGRAM_TITLE_MAX_LENGTH} символов.",
                "emoji": "❌ Telegram не разрешает emoji в титуле.",
            }
            await update.message.reply_text(messages.get(str(error), "❌ Некорректный титул."))
            return
        payload = {"kind": "telegram_title_confirm", "title": title}
        _save_draft(context, update.effective_chat.id, payload)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Установить", callback_data=f"shop_title_confirm_{context.tg_user.tg_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"shop_title_clear_draft_{context.tg_user.tg_id}"),
        ]])
        await update.message.reply_text(
            "🏷 <b>Предпросмотр титула</b>\n\n"
            f"{html_escape(context.tg_user.full_username())}  <b>{html_escape(title)}</b>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    # Confirmation drafts do not consume arbitrary chat messages.


@ensure_game
async def handle_shop_draft_cancel_callback(update: Update, context: ECallbackContext):
    query = update.callback_query
    owner_id = _owner_id(query.data)
    if await _reject_foreign_shop(query, owner_id):
        return
    _delete_draft(context, update.effective_chat.id)
    await query.edit_message_text("❌ Покупка отменена. Койны не списывались.")
    await query.answer()
