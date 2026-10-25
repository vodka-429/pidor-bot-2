"""Manual, persistent changelog announcements for substantial releases."""
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, List

from sqlmodel import select

from bot.app.models import ChangelogReceipt, Game
from bot.handlers.game.commands import current_datetime
from bot.handlers.game.config import GameConstants, get_config


CURRENT_RELEASE_ID = "2026-09-economy-pilot"
RANDOM_START_RELEASE_ID = "2026-10-random-start"
COIN_DUEL_RELEASE_ID = "2026-10-coin-duel"
DOUBLE_CHANCE_PRICE_RELEASE_ID = "2026-10-double-chance-price"
DEPOSIT_RELEASE_ID = "2026-10-deposits"

# Окно "свежести" релиза и минимальный размер набора новостей.
CHANGELOG_WINDOW_DAYS = 30
CHANGELOG_MIN_RELEASES = 3
TELEGRAM_MESSAGE_LIMIT = 4096
SECTION_SEPARATOR = "\n\n─────\n\n"
CHANGELOG_FOOTER = "Перечитать новости: /pidornews"


def build_random_start_changelog_html() -> str:
    return (
        "🆕 <b>Случайное время розыгрыша</b>\n\n"
        "После каждого розыгрыша бот назначает время открытия на следующий "
        "календарный день: случайный целый час от <b>00:00 до 18:00 МСК</b>. "
        "Время появляется в сообщении с результатом.\n\n"
        "До назначенного часа /pidor покажет время открытия и сколько осталось ждать. "
        "С этого часа запуск доступен до конца дня - всегда не меньше шести часов.\n\n"
        "Перевыбор время не меняет. Если день пропущен, на следующий день запуск "
        "снова доступен сразу."
    )


def build_coin_duel_changelog_html(constants: GameConstants) -> str:
    return (
        "🆕 <b>Раз на раз</b>\n\n"
        "🥊 Вызови в /pidorshop того, кто богаче тебя. "
        f"Ставишь до {constants.duel_max_stake}, он отвечает в 1-{constants.duel_max_leverage} "
        "раза больше, смотря насколько он жирнее. Обе ставки списываются сразу, "
        "разборка на завтрашнем розыгрыше, кости кидает бот, победитель забирает всё "
        "(минус комиссия с выигрыша).\n\n"
        f"🚔 Не хочешь драки - вызови ментов за {constants.police_price}: все разборки "
        "на завтра отменятся, ставки вернутся. Но весь чат узнает, кто позвонил."
    )


def build_current_changelog_html(constants: GameConstants) -> str:
    """Build the current announcement from features available in this chat."""
    feature_lines = []
    if constants.coin_rain_enabled:
        feature_lines.append(
            "🌧 <b>Койновый дождь</b> - раздайте койны случайным "
            "участникам чата."
        )
    if constants.custom_phrase_enabled:
        feature_lines.append(
            "✍️ <b>Победная фраза</b> - настройте свою постоянную фразу "
            "победителя."
        )
    if constants.telegram_title_enabled:
        feature_lines.append(
            "🏷 <b>Telegram-титулы</b> - тестовая функция, пока с нюансами. "
            "Владельцу чата и части администраторов нужно поставить титул вручную, "
            "после чего бот его проверит."
        )

    sections = ["🆕 <b>Что нового в PidorBot</b>"]
    if feature_lines:
        sections.append("\n".join(feature_lines))
    sections.append("Подробности и покупки: /pidorshop")
    return "\n\n".join(sections)


@dataclass(frozen=True)
class Release:
    id: str
    released_on: date
    is_enabled: Callable[[GameConstants], bool]
    build_html: Callable[[GameConstants], str]


# Новая фича = одна запись здесь.
def build_double_chance_price_changelog_html(constants: GameConstants) -> str:
    base = constants.double_chance_price
    step = constants.double_chance_price_step
    return (
        "🎲 <b>Растущая цена двойного шанса</b>\n\n"
        "Цена двойного шанса растёт для каждого следующего покупателя "
        "на одного и того же игрока в один и тот же день. "
        f"Первый платит <b>{base} 🪙</b>, второй - <b>{base + step} 🪙</b>, "
        f"третий - <b>{base + 2 * step} 🪙</b> и так далее (+{step} за каждый).\n\n"
        "Другой игрок или другой день цену не меняют. Шанс действует "
        "один день - в завтрашнем розыгрыше.\n\n"
        "Цена видна прямо на кнопках выбора игрока: <b>Имя ×2 · "
        f"{base + 2 * step}🪙</b>. Если пока вы выбирали, кто-то успел купить раньше, "
        "бот покажет новую цену и обновит кнопки - деньги не спишутся."
    )


def build_deposit_changelog_html(constants: GameConstants) -> str:
    return (
        "💼 <b>Вклады</b>\n\n"
        "В /pidorshop появилась кнопка <b>Вклад</b>: положи койны на 7, 14 или 30 дней "
        "и забери их с процентами. Процент берётся из ключевой ставки ЦБ в момент "
        "открытия и дальше не меняется; в игре это ставка за 30 дней, на 14 дней - "
        "половина, на 7 дней - четверть. До "
        f"{constants.deposit_max_amount} 🪙, один вклад на игрока.\n\n"
        "Проценты платит банк чата. Если в банке не хватает койнов на проценты, "
        "вклады закрыты. Выплата - одним платежом в конце срока: бот добавит её "
        "строкой в сообщение /pidor. Досрочное снятие возвращает койны, но проценты сгорают.\n\n"
        "Вклад считается в твоём богатстве: по нему тебя можно вызвать раз на раз, "
        "а если на руках не хватит на ставку, вклад арестуют до разборки, а проигрыш "
        "закроет его досрочно."
    )


RELEASES = [
    Release(
        id=CURRENT_RELEASE_ID,
        released_on=date(2026, 9, 26),
        is_enabled=lambda constants: True,
        build_html=build_current_changelog_html,
    ),
    Release(
        id=RANDOM_START_RELEASE_ID,
        released_on=date(2026, 10, 17),
        is_enabled=lambda constants: constants.random_start_enabled,
        build_html=lambda constants: build_random_start_changelog_html(),
    ),
    Release(
        id=COIN_DUEL_RELEASE_ID,
        released_on=date(2026, 10, 23),
        is_enabled=lambda constants: constants.duel_enabled,
        build_html=build_coin_duel_changelog_html,
    ),
    Release(
        id=DOUBLE_CHANCE_PRICE_RELEASE_ID,
        released_on=date(2026, 10, 24),
        is_enabled=lambda constants: (
            constants.double_chance_enabled and constants.double_chance_price_step > 0
        ),
        build_html=build_double_chance_price_changelog_html,
    ),
    Release(
        id=DEPOSIT_RELEASE_ID,
        released_on=date(2026, 10, 24),
        is_enabled=lambda constants: constants.deposit_enabled,
        build_html=build_deposit_changelog_html,
    ),
]


def select_releases(constants: GameConstants) -> List[Release]:
    """Включённые в чате релизы: свежие (окно) или последние минимум, свежие сверху."""
    enabled = sorted(
        (release for release in RELEASES if release.is_enabled(constants)),
        key=lambda release: release.released_on,
        reverse=True,
    )
    threshold = current_datetime().date() - timedelta(days=CHANGELOG_WINDOW_DAYS)
    fresh = [release for release in enabled if release.released_on >= threshold]
    if len(fresh) >= CHANGELOG_MIN_RELEASES:
        return fresh
    return enabled[:CHANGELOG_MIN_RELEASES]


def split_into_messages(sections: List[str]) -> List[List[int]]:
    """Сгруппировать индексы секций в сообщения до лимита Telegram (границы - между релизами)."""
    groups: List[List[int]] = []
    current: List[int] = []
    length = 0
    for index, section in enumerate(sections):
        added = len(section) + (len(SECTION_SEPARATOR) if current else 0)
        if current and length + added > TELEGRAM_MESSAGE_LIMIT:
            groups.append(current)
            current, length, added = [], 0, len(section)
        current.append(index)
        length += added
    if current:
        groups.append(current)
    return groups


async def send_current_changelog(update, context, mark_as_seen: bool) -> bool:
    config = get_config(update.effective_chat.id)
    constants = config.constants
    if not constants.changelog_enabled:
        return False

    releases = select_releases(constants)
    if mark_as_seen:
        context.db_session.exec(
            select(Game).where(Game.id == context.game.id).with_for_update()
        ).first()
        seen = set(context.db_session.exec(
            select(ChangelogReceipt.release_id).where(
                ChangelogReceipt.game_id == context.game.id,
            )
        ).all())
        releases = [release for release in releases if release.id not in seen]
    if not releases:
        return False

    sections = [release.build_html(constants) for release in releases]
    messages = [
        (SECTION_SEPARATOR.join(sections[i] for i in group), group)
        for group in split_into_messages(sections)
    ]
    footer = "\n\n" + CHANGELOG_FOOTER
    last_text, last_group = messages[-1]
    if len(last_text) + len(footer) <= TELEGRAM_MESSAGE_LIMIT:
        messages[-1] = (last_text + footer, last_group)
    else:
        messages.append((CHANGELOG_FOOTER, []))

    for text, group in messages:
        await update.effective_chat.send_message(text, parse_mode="HTML")
        if mark_as_seen and group:
            for i in group:
                context.db_session.add(ChangelogReceipt(
                    game_id=context.game.id,
                    release_id=releases[i].id,
                ))
            context.db_session.commit()
    return True
