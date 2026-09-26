"""Manual, persistent changelog announcements for substantial releases."""
from sqlmodel import select

from bot.app.models import ChangelogReceipt, Game
from bot.handlers.game.config import GameConstants, get_config


CURRENT_RELEASE_ID = "2026-09-economy-pilot"


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


async def send_current_changelog(update, context, mark_as_seen: bool) -> bool:
    config = get_config(update.effective_chat.id)
    if not config.constants.changelog_enabled:
        return False

    if mark_as_seen:
        context.db_session.exec(
            select(Game).where(Game.id == context.game.id).with_for_update()
        ).first()
        existing = context.db_session.exec(
            select(ChangelogReceipt).where(
                ChangelogReceipt.game_id == context.game.id,
                ChangelogReceipt.release_id == CURRENT_RELEASE_ID,
            )
        ).first()
        if existing is not None:
            return False

    changelog_html = build_current_changelog_html(config.constants)
    await update.effective_chat.send_message(changelog_html, parse_mode="HTML")
    if mark_as_seen:
        context.db_session.add(ChangelogReceipt(
            game_id=context.game.id,
            release_id=CURRENT_RELEASE_ID,
        ))
        context.db_session.commit()
    return True
