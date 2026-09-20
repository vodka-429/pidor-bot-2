"""Manual, persistent changelog announcements for substantial releases."""
from sqlmodel import select

from bot.app.models import ChangelogReceipt, Game
from bot.handlers.game.config import get_config


CURRENT_RELEASE_ID = "2026-09-economy-pilot"
CURRENT_CHANGELOG_HTML = """🆕 <b>Что нового в PidorBot</b>

🌧 <b>Койновый дождь</b> — раздайте койны случайным участникам чата.
✍️ <b>Победная фраза</b> — настройте свою постоянную фразу победителя.
🏷 <b>Telegram-титулы</b> — новая тестовая функция, пока с нюансами. Владельцу чата и части администраторов нужно поставить титул вручную, после чего бот его проверит.
🏪 Магазин стал компактнее: теперь кнопки расположены по две в строке.

Подробности и покупки: /pidorshop
Эту новость всегда можно открыть командой /pidornews"""


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

    await update.effective_chat.send_message(CURRENT_CHANGELOG_HTML, parse_mode="HTML")
    if mark_as_seen:
        context.db_session.add(ChangelogReceipt(
            game_id=context.game.id,
            release_id=CURRENT_RELEASE_ID,
        ))
        context.db_session.commit()
    return True
