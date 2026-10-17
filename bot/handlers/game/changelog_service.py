"""Manual, persistent changelog announcements for substantial releases."""
from datetime import datetime

from sqlmodel import select

from bot.app.models import ChangelogReceipt, Game
from bot.handlers.game.config import GameConstants, get_config
from bot.handlers.game.draw_schedule_service import MOSCOW_TZ, random_start_active


CURRENT_RELEASE_ID = "2026-09-economy-pilot"
RANDOM_START_RELEASE_ID = "2026-10-random-start"


def build_random_start_changelog_html() -> str:
    return (
        "🆕 <b>Случайное время розыгрыша</b>\n\n"
        "Первый розыгрыш после обновления можно запустить как обычно. "
        "После него бот назначит время открытия на следующий календарный день: "
        "случайный целый час от <b>00:00 до 18:00 МСК</b>. "
        "Время появится в сообщении с результатом.\n\n"
        "До назначенного часа /pidor покажет время открытия и сколько осталось ждать. "
        "С этого часа запуск доступен до конца дня — всегда не меньше шести часов.\n\n"
        "Перевыбор время не меняет. Если день пропущен, на следующий день запуск "
        "снова доступен сразу.\n\n"
        "Перечитать новость: /pidornews"
    )


def build_current_changelog_html(constants: GameConstants) -> str:
    """Build the current announcement from features available in this chat."""
    feature_lines = []
    if constants.coin_rain_enabled:
        feature_lines.append(
            "🌧 <b>Койновый дождь</b> — раздайте койны случайным "
            "участникам чата."
        )
    if constants.custom_phrase_enabled:
        feature_lines.append(
            "✍️ <b>Победная фраза</b> — настройте свою постоянную фразу "
            "победителя."
        )
    if constants.telegram_title_enabled:
        feature_lines.append(
            "🏷 <b>Telegram-титулы</b> — новая тестовая функция, пока с нюансами. "
            "Владельцу чата и части администраторов нужно поставить титул вручную, "
            "после чего бот его проверит."
        )

    sections = ["🆕 <b>Что нового в PidorBot</b>"]
    if feature_lines:
        sections.append("\n".join(feature_lines))
    sections.extend([
        "🏪 Магазин стал компактнее: теперь кнопки расположены по две в строке.",
        "Подробности и покупки: /pidorshop\n"
        "Эту новость всегда можно открыть командой /pidornews",
    ])
    return "\n\n".join(sections)


async def send_current_changelog(
    update, context, mark_as_seen: bool, now: datetime | None = None,
) -> bool:
    config = get_config(update.effective_chat.id)
    if not config.constants.changelog_enabled:
        return False

    now = now if now is not None else datetime.now(tz=MOSCOW_TZ)
    scheduled = random_start_active(config.constants, now)
    release_id = RANDOM_START_RELEASE_ID if scheduled else CURRENT_RELEASE_ID

    if mark_as_seen:
        context.db_session.exec(
            select(Game).where(Game.id == context.game.id).with_for_update()
        ).first()
        existing = context.db_session.exec(
            select(ChangelogReceipt).where(
                ChangelogReceipt.game_id == context.game.id,
                ChangelogReceipt.release_id == release_id,
            )
        ).first()
        if existing is not None:
            return False

    changelog_html = (
        build_random_start_changelog_html()
        if scheduled else build_current_changelog_html(config.constants)
    )
    await update.effective_chat.send_message(changelog_html, parse_mode="HTML")
    if mark_as_seen:
        context.db_session.add(ChangelogReceipt(
            game_id=context.game.id,
            release_id=release_id,
        ))
        context.db_session.commit()
    return True
