"""Manual, persistent changelog announcements for substantial releases."""
from sqlmodel import select

from bot.app.models import ChangelogReceipt, Game
from bot.handlers.game.config import GameConstants, get_config


CURRENT_RELEASE_ID = "2026-09-economy-pilot"
RANDOM_START_RELEASE_ID = "2026-10-random-start"
COIN_DUEL_RELEASE_ID = "2026-10-coin-duel"


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


def build_coin_duel_changelog_html(constants: GameConstants) -> str:
    return (
        "🆕 <b>Раз на раз</b>\n\n"
        "🥊 Вызови в /pidorshop того, кто богаче тебя. "
        f"Ставишь до {constants.duel_max_stake}, он отвечает в 1-{constants.duel_max_leverage} "
        "раза больше, смотря насколько он жирнее. Обе ставки списываются сразу, "
        "разборка на завтрашнем розыгрыше, кости кидает бот, победитель забирает всё "
        "(минус комиссия в банк).\n\n"
        f"🚔 Не хочешь драки - вызови ментов за {constants.police_price}: все разборки "
        "на завтра отменятся, ставки вернутся. Но весь чат узнает, кто позвонил.\n\n"
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


async def send_current_changelog(update, context, mark_as_seen: bool) -> bool:
    config = get_config(update.effective_chat.id)
    if not config.constants.changelog_enabled:
        return False

    constants = config.constants
    if constants.duel_enabled:
        release_id = COIN_DUEL_RELEASE_ID
        build_html = build_coin_duel_changelog_html
    elif constants.random_start_enabled:
        release_id = RANDOM_START_RELEASE_ID
        build_html = lambda _constants: build_random_start_changelog_html()
    else:
        release_id = CURRENT_RELEASE_ID
        build_html = build_current_changelog_html

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

    changelog_html = build_html(constants)
    await update.effective_chat.send_message(changelog_html, parse_mode="HTML")
    if mark_as_seen:
        context.db_session.add(ChangelogReceipt(
            game_id=context.game.id,
            release_id=release_id,
        ))
        context.db_session.commit()
    return True
