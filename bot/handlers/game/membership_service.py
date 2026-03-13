"""
Сервис проверки членства пользователей в чате.
Деактивирует игроков, которые вышли из чата или были кикнуты.
"""
import asyncio

from sqlmodel import select

from bot.app.models import GamePlayer, TGUser


def get_active_players(db_session, game_id: int) -> list:
    """Возвращает список активных игроков (TGUser) для указанной игры."""
    stmt = (
        select(TGUser)
        .join(GamePlayer, (GamePlayer.user_id == TGUser.id) & (GamePlayer.game_id == game_id))
        .where(GamePlayer.is_active == True)
    )
    return db_session.exec(stmt).all()


def get_deactivated_player_ids(db_session, game_id: int) -> set:
    """Возвращает множество user_id деактивированных игроков."""
    stmt = select(GamePlayer.user_id).where(
        GamePlayer.game_id == game_id,
        GamePlayer.is_active == False,
    )
    return set(db_session.exec(stmt).all())


def deactivate_player(db_session, game_id: int, user_id: int) -> None:
    """Деактивирует игрока в данной игре."""
    stmt = select(GamePlayer).where(
        GamePlayer.game_id == game_id,
        GamePlayer.user_id == user_id,
    )
    game_player = db_session.exec(stmt).first()
    if game_player and game_player.is_active:
        game_player.is_active = False
        db_session.add(game_player)
        db_session.commit()


def reactivate_player(db_session, game_id: int, user_id: int) -> None:
    """Реактивирует деактивированного игрока."""
    stmt = select(GamePlayer).where(
        GamePlayer.game_id == game_id,
        GamePlayer.user_id == user_id,
    )
    game_player = db_session.exec(stmt).first()
    if game_player and not game_player.is_active:
        game_player.is_active = True
        db_session.add(game_player)
        db_session.commit()


async def check_player_membership(bot, chat_id: int, db_session, game_id: int, player) -> None:
    """
    Проверяет членство одного игрока в чате через Telegram API.
    При ошибке API — оставляет активным (safe default).
    Деактивирует только при явном статусе 'left' или 'kicked'.
    """
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=player.tg_id)
        if member.status in ('left', 'kicked'):
            deactivate_player(db_session, game_id, player.id)
    except Exception:
        pass  # safe default: keep active on any API error


async def batch_check_membership(bot, chat_id: int, db_session, game_id: int, players: list) -> None:
    """
    Проверяет членство всех переданных игроков в чате.
    Выполняет запросы параллельно.
    """
    await asyncio.gather(*[
        check_player_membership(bot, chat_id, db_session, game_id, player)
        for player in players
    ])


async def remove_inactive_players(bot, chat_id: int, db_session, game_id: int) -> list:
    """
    Проверяет всех активных игроков через Telegram API и деактивирует вышедших.
    Возвращает список деактивированных TGUser.
    """
    players = get_active_players(db_session, game_id)
    deactivated = []
    for player in players:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=player.tg_id)
            if member.status in ('left', 'kicked'):
                deactivate_player(db_session, game_id, player.id)
                deactivated.append(player)
        except Exception:
            pass  # safe default: keep active on any API error
    return deactivated
