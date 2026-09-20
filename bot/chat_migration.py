"""Idempotent database migration for Telegram group-to-supergroup moves."""

import logging

from sqlmodel import Session, select

from bot.app.models import Game, KVItem


logger = logging.getLogger(__name__)


def migrate_configured_chat_ids(engine, migrations: dict[int, int]) -> None:
    """Move chat-addressed state to new Telegram IDs before polling starts.

    Telegram assigns a new ID when a basic group becomes a supergroup. Game
    state is linked through ``Game``, while drafts and chat-level counters live
    in ``KVItem``. Refuse ambiguous merges instead of silently losing data.
    """
    if not migrations:
        return

    with Session(engine) as session:
        changed = False
        for old_chat_id, new_chat_id in migrations.items():
            if old_chat_id == new_chat_id:
                continue

            old_game = session.exec(
                select(Game).where(Game.chat_id == old_chat_id)
            ).one_or_none()
            new_game = session.exec(
                select(Game).where(Game.chat_id == new_chat_id)
            ).one_or_none()
            if old_game is not None and new_game is not None and old_game.id != new_game.id:
                raise RuntimeError(
                    f"Cannot migrate chat {old_chat_id} to {new_chat_id}: both games exist"
                )

            old_items = session.exec(
                select(KVItem).where(KVItem.chat_id == old_chat_id)
            ).all()
            new_keys = {
                item.key
                for item in session.exec(
                    select(KVItem).where(KVItem.chat_id == new_chat_id)
                ).all()
            }
            collisions = sorted(item.key for item in old_items if item.key in new_keys)
            if collisions:
                raise RuntimeError(
                    f"Cannot migrate chat {old_chat_id} to {new_chat_id}: "
                    f"KV keys already exist: {collisions}"
                )

            if old_game is not None:
                old_game.chat_id = new_chat_id
                session.add(old_game)
                changed = True
            for item in old_items:
                item.chat_id = new_chat_id
                session.add(item)
                changed = True

            if old_game is not None or old_items:
                logger.info(
                    "Migrating Telegram chat state: old_chat_id=%s new_chat_id=%s "
                    "game_id=%s kv_items=%s",
                    old_chat_id,
                    new_chat_id,
                    old_game.id if old_game else None,
                    len(old_items),
                )

        if changed:
            session.commit()
            logger.info("Configured Telegram chat migrations committed")
