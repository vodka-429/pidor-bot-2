"""
Извлекает дни рождения зарегистрированных игроков из Telegram через MTProto.

Запуск:
    TELEGRAM_API_ID=... TELEGRAM_API_HASH=... DATABASE_URL=... \\
        python scripts/extract_birthdays.py [--game-id N] [--tg-ids 1,2,3]

ТРЕБОВАНИЯ:
  • Telethon >= 1.36 (поле `birthday` появилось в Layer 181).
    Проверить: `python -c "import telethon; print(telethon.__version__)"`
    Обновить: `pip install -U "telethon>=1.36"`

При первом запуске Telethon попросит код подтверждения и сохранит сессию
в `birthday_extract.session`. Скрипт сразу прогревает кэш через get_dialogs(),
чтобы Telegram отдал access_hash для игроков, которых ты «знаешь»
(переписки/общие чаты/контакты).

Логика резолва entity:
  1. Кэш Telethon после get_dialogs()
  2. Если есть username — fallback через client.get_entity('username')
  3. Если оба не сработали — записывается в missing

Вывод: готовый кусок для вставки в миграцию, например:
    BIRTHDAYS = {
        12345: (3, 15),
        67890: (11, 7),
    }
    # Missing: [11111, 22222]

ВНИМАНИЕ: поле birthday в Telegram доступно только если игрок:
  1) указал его в профиле, и
  2) разрешил видеть либо всем, либо контактам (включая тебя).
"""
import argparse
import asyncio
import os
import sys
from typing import Dict, List, Optional, Tuple

from sqlmodel import Session, create_engine, select
from telethon import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest

# Чтобы скрипт работал из корня проекта без установки пакета
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.app.models import GamePlayer, TGUser  # noqa: E402


SESSION_NAME = 'birthday_extract'


class Target:
    __slots__ = ('tg_id', 'username', 'display')

    def __init__(self, tg_id: int, username: Optional[str], display: str):
        self.tg_id = tg_id
        self.username = username
        self.display = display


def load_targets_from_db(game_id: Optional[int]) -> List[Target]:
    db_url = os.environ['DATABASE_URL']
    engine = create_engine(db_url)
    with Session(engine) as session:
        if game_id is not None:
            stmt = (
                select(TGUser)
                .join(GamePlayer, GamePlayer.user_id == TGUser.id)
                .where(GamePlayer.game_id == game_id, GamePlayer.is_active == True)  # noqa: E712
            )
        else:
            stmt = select(TGUser)
        users = session.exec(stmt).all()
        return [Target(u.tg_id, u.username, u.full_username()) for u in users]


def _check_telethon_version() -> None:
    try:
        import telethon
        ver = tuple(int(x) for x in telethon.__version__.split('.')[:2])
        if ver < (1, 36):
            print(
                f'⚠️  Telethon {telethon.__version__} слишком старый.\n'
                f'   Поле `birthday` появилось в 1.36+. Обнови: pip install -U "telethon>=1.36"',
                file=sys.stderr,
            )
            sys.exit(2)
    except Exception:
        pass  # на всякий случай не блокируем


async def _resolve_entity(client: TelegramClient, t: Target):
    """Пытается резолвить пользователя: сначала по id (после dialogs), потом по username."""
    # 1) Прямой резолв из локального кэша Telethon
    try:
        return await client.get_input_entity(t.tg_id)
    except (ValueError, Exception):
        pass

    # 2) Fallback через username (работает для публичных аккаунтов)
    if t.username:
        try:
            return await client.get_entity(t.username)
        except Exception:
            pass

    return None


async def fetch_birthdays(targets: List[Target]) -> Tuple[Dict[int, Tuple[int, int]], List[Tuple[int, str, str]]]:
    api_id = int(os.environ['TELEGRAM_API_ID'])
    api_hash = os.environ['TELEGRAM_API_HASH']

    found: Dict[int, Tuple[int, int]] = {}
    missing: List[Tuple[int, str, str]] = []  # (tg_id, display, reason)

    async with TelegramClient(SESSION_NAME, api_id, api_hash) as client:
        # Прогреваем кэш — подтягиваем диалоги, чтобы Telegram отдал access_hash
        print('Прогреваю кэш диалогов (get_dialogs)...', file=sys.stderr)
        dialog_count = 0
        async for _ in client.iter_dialogs():
            dialog_count += 1
        print(f'  Загружено {dialog_count} диалогов', file=sys.stderr)

        for t in targets:
            try:
                entity = await _resolve_entity(client, t)
                if entity is None:
                    missing.append((t.tg_id, t.display, 'entity not resolved (no dialog, no public username)'))
                    continue

                full = await client(GetFullUserRequest(entity))
                # В Telethon <1.36 поля birthday не существует
                birthday = getattr(full.full_user, 'birthday', None)
                if birthday is None:
                    missing.append((t.tg_id, t.display, 'birthday not set / hidden'))
                else:
                    found[t.tg_id] = (birthday.month, birthday.day)
                    print(f'  ✓ {t.display} ({t.tg_id}): {birthday.day:02d}.{birthday.month:02d}', file=sys.stderr)
            except Exception as e:
                missing.append((t.tg_id, t.display, type(e).__name__ + ': ' + str(e)))
            # Бережём API от флуд-лимитов
            await asyncio.sleep(0.3)

    return found, missing


def print_migration_block(found: Dict[int, Tuple[int, int]], missing: List[Tuple[int, str, str]]) -> None:
    print()
    print('# === Вставь в миграцию ===')
    print('BIRTHDAYS = {')
    for tg_id, (m, d) in sorted(found.items()):
        print(f'    {tg_id}: ({m}, {d}),')
    print('}')
    print()
    if missing:
        print(f'# Missing ({len(missing)}) — добей вручную:')
        for tg_id, display, reason in missing:
            print(f'#   {tg_id} ({display}): {reason}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-id', type=int, default=None,
                        help='Брать активных игроков только этой игры. По умолчанию — все TGUser.')
    parser.add_argument('--tg-ids', type=str, default=None,
                        help='Список tg_id через запятую (перебивает --game-id и БД).')
    args = parser.parse_args()

    _check_telethon_version()

    if args.tg_ids:
        targets = [Target(int(x.strip()), None, f'<id={x.strip()}>')
                   for x in args.tg_ids.split(',') if x.strip()]
    else:
        targets = load_targets_from_db(args.game_id)

    if not targets:
        print('Нет tg_id для проверки.', file=sys.stderr)
        sys.exit(1)

    print(f'Проверяю {len(targets)} пользователей...', file=sys.stderr)
    found, missing = asyncio.run(fetch_birthdays(targets))
    print_migration_block(found, missing)


if __name__ == '__main__':
    main()
