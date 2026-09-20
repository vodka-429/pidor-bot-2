import pytest
from sqlmodel import Session, SQLModel, create_engine

from bot.app.models import Game, KVItem
from bot.chat_migration import migrate_configured_chat_ids


@pytest.fixture
def migration_engine():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.mark.unit
def test_migrate_configured_chat_ids_moves_game_and_kv_state(migration_engine):
    with Session(migration_engine) as session:
        session.add(Game(chat_id=-123))
        session.add(KVItem(chat_id=-123, key="shop_draft_1", value="{}"))
        session.commit()

    migrate_configured_chat_ids(migration_engine, {-123: -100123})

    with Session(migration_engine) as session:
        assert session.query(Game).filter_by(chat_id=-123).one_or_none() is None
        assert session.query(Game).filter_by(chat_id=-100123).one().id is not None
        assert session.query(KVItem).filter_by(chat_id=-123).all() == []
        assert session.query(KVItem).filter_by(chat_id=-100123).one().key == "shop_draft_1"

    # Startup migration is idempotent after the old records are gone.
    migrate_configured_chat_ids(migration_engine, {-123: -100123})


@pytest.mark.unit
def test_migrate_configured_chat_ids_refuses_ambiguous_game_merge(migration_engine):
    with Session(migration_engine) as session:
        session.add(Game(chat_id=-123))
        session.add(Game(chat_id=-100123))
        session.commit()

    with pytest.raises(RuntimeError, match="both games exist"):
        migrate_configured_chat_ids(migration_engine, {-123: -100123})


@pytest.mark.unit
def test_migrate_configured_chat_ids_refuses_kv_collision(migration_engine):
    with Session(migration_engine) as session:
        session.add(KVItem(chat_id=-123, key="same", value="old"))
        session.add(KVItem(chat_id=-100123, key="same", value="new"))
        session.commit()

    with pytest.raises(RuntimeError, match="KV keys already exist"):
        migrate_configured_chat_ids(migration_engine, {-123: -100123})
