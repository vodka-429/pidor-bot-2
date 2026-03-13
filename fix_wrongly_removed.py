"""
Скрипт для восстановления игроков, ошибочно деактивированных командой /pidorremove.

Что делает:
1. Находит всех деактивированных игроков в указанном чате
2. Проверяет через Telegram API — реально ли они вышли
3. Реактивирует тех, кто ещё в чате
4. Даёт им 44 монеты как компенсацию
5. Пишет итог в чат

Dry-run (только посмотреть, ничего не меняет):
    CHAT_ID=-1001392307997 DRY_RUN=1 python fix_wrongly_removed.py

Боевой запуск:
    CHAT_ID=-1001392307997 python fix_wrongly_removed.py
"""

import asyncio
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlmodel import Session, create_engine, select
from telegram import Bot
from telegram.error import BadRequest

load_dotenv()

CHAT_ID = int(os.environ['CHAT_ID'])
DRY_RUN = os.environ.get('DRY_RUN', '0') == '1'
EXCLUDE = {u.strip().lstrip('@') for u in os.environ.get('EXCLUDE', '').split(',') if u.strip()}
COINS_COMPENSATION = 44
CURRENT_YEAR = datetime.now(tz=ZoneInfo('Europe/Moscow')).year


def get_engine():
    dburi = os.environ['DATABASE_URL']
    if dburi.startswith('postgres://'):
        dburi = dburi.replace('postgres://', 'postgresql://', 1)
    return create_engine(dburi, echo=False)


async def main():
    from bot.app.models import Game, GamePlayer, TGUser
    from bot.handlers.game.coin_service import add_coins
    from bot.handlers.game.membership_service import reactivate_player

    if DRY_RUN:
        print('=== DRY RUN — ничего не меняется ===\n')

    engine = get_engine()

    async with Bot(os.environ['TELEGRAM_BOT_API_SECRET']) as bot:
        with Session(engine) as db:
            game = db.exec(select(Game).where(Game.chat_id == CHAT_ID)).first()
            if not game:
                print(f'Игра для чата {CHAT_ID} не найдена')
                return

            stmt = (
                select(TGUser)
                .join(GamePlayer, (GamePlayer.user_id == TGUser.id) & (GamePlayer.game_id == game.id))
                .where(GamePlayer.is_active == False)
            )
            deactivated_players = db.exec(stmt).all()
            print(f'Деактивированных игроков: {len(deactivated_players)}')

            restored = []
            still_gone = []

            for player in deactivated_players:
                definitely_gone = False
                reason = ''
                try:
                    member = await bot.get_chat_member(chat_id=CHAT_ID, user_id=player.tg_id)
                    if member.status in ('left', 'kicked'):
                        definitely_gone = True
                        reason = member.status
                except BadRequest as e:
                    if 'user not found' in str(e).lower():
                        definitely_gone = True
                        reason = 'user not found'
                    # Иначе (Participant_id_invalid и т.п.) — не можем проверить, восстанавливаем
                except Exception:
                    pass  # не можем проверить — восстанавливаем

                if definitely_gone or player.username in EXCLUDE:
                    still_gone.append(player)
                    tag = f'вручную исключён' if player.username in EXCLUDE else f'реально вышел ({reason})'
                    print(f'  ❌ {tag}: {player.full_username()}')
                else:
                    restored.append(player)
                    print(f'  ✅ Будет восстановлен: {player.full_username()}')
                    if not DRY_RUN:
                        reactivate_player(db, game.id, player.id)
                        add_coins(db, game.id, player.id, COINS_COMPENSATION, CURRENT_YEAR, reason='compensation')

            if not restored:
                print('\nНикого восстанавливать не нужно.')
                return

            names = ', '.join(f'@{p.username}' if p.username else p.first_name for p in restored)
            message = (
                f'мне стыдно. ии <s>муцураев</s> вызывает аутизм.\n\n'
                f'бот ошибочно удалил из игры: {names}\n\n'
                f'все восстановлены, каждому {COINS_COMPENSATION} монет.'
            )

            print(f'\n--- Сообщение в чат ---\n{message}\n-----------------------')

            if DRY_RUN:
                print('\nDRY RUN — сообщение не отправлено, БД не изменена.')
            else:
                await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode='HTML')
                print(f'\nГотово. Восстановлено: {len(restored)}, осталось деактивированных: {len(still_gone)}')


if __name__ == '__main__':
    asyncio.run(main())
