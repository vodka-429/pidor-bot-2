import json
from unittest.mock import patch

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from bot.app.models import (
    ChatBank,
    CoinRainPurchase,
    Game,
    GamePlayer,
    PidorCoinTransaction,
    TGUser,
)
from bot.handlers.game.config import ChatConfig, GameConstants
from bot.handlers.game.economy_pilot_service import (
    execute_coin_rain,
    render_custom_victory_phrase,
    validate_custom_phrase,
    validate_telegram_title,
)


@pytest.fixture
def economy_session():
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        game = Game(chat_id=-1001)
        session.add(game)
        session.commit()
        session.refresh(game)

        players = []
        for index in range(6):
            player = TGUser(
                tg_id=1000 + index,
                username=f"player{index}",
                first_name=f"Player {index}",
            )
            session.add(player)
            session.commit()
            session.refresh(player)
            session.add(GamePlayer(game_id=game.id, user_id=player.id, is_active=True))
            session.add(PidorCoinTransaction(
                game_id=game.id,
                user_id=player.id,
                amount=100,
                year=2026,
                reason="seed",
            ))
            players.append(player)
        session.commit()
        yield session, game, players


def _pilot_config():
    return ChatConfig(
        chat_id=-1001,
        constants=GameConstants(coin_rain_enabled=True),
    )


@pytest.mark.unit
def test_coin_rain_distributes_five_rewards_and_banks_all_remainder(economy_session):
    session, game, players = economy_session
    with patch(
        "bot.handlers.game.economy_pilot_service.get_config_by_game_id",
        return_value=_pilot_config(),
    ), patch("bot.handlers.game.economy_pilot_service.random.sample", side_effect=lambda values, count: values[:count]):
        success, reason, recipients, bank_amount = execute_coin_rain(
            session, game.id, players[0].id, players, 2026, 263
        )

    assert (success, reason) == (True, "success")
    assert len(recipients) == 5
    assert bank_amount == 15
    bank = session.exec(select(ChatBank).where(ChatBank.game_id == game.id)).one()
    assert bank.balance == 15
    purchase = session.exec(select(CoinRainPurchase)).one()
    assert purchase.distributed_amount == 25
    assert json.loads(purchase.recipient_ids) == [player.id for player in players[1:]]


@pytest.mark.unit
def test_coin_rain_with_three_recipients_sends_twenty_five_to_bank(economy_session):
    session, game, players = economy_session
    available = players[:4]
    with patch(
        "bot.handlers.game.economy_pilot_service.get_config_by_game_id",
        return_value=_pilot_config(),
    ), patch("bot.handlers.game.economy_pilot_service.random.sample", side_effect=lambda values, count: values[:count]):
        success, _, recipients, bank_amount = execute_coin_rain(
            session, game.id, players[0].id, available, 2026, 264
        )

    assert success is True
    assert len(recipients) == 3
    assert bank_amount == 25


@pytest.mark.unit
def test_coin_rain_enforces_buyer_and_chat_daily_limits(economy_session):
    session, game, players = economy_session
    with patch(
        "bot.handlers.game.economy_pilot_service.get_config_by_game_id",
        return_value=_pilot_config(),
    ), patch("bot.handlers.game.economy_pilot_service.random.sample", side_effect=lambda values, count: values[:count]):
        assert execute_coin_rain(session, game.id, players[0].id, players, 2026, 265)[0] is True
        assert execute_coin_rain(session, game.id, players[0].id, players, 2026, 265)[1] == "buyer_daily_limit"
        assert execute_coin_rain(session, game.id, players[1].id, players, 2026, 265)[0] is True
        assert execute_coin_rain(session, game.id, players[2].id, players, 2026, 265)[0] is True
        assert execute_coin_rain(session, game.id, players[3].id, players, 2026, 265)[1] == "chat_daily_limit"


@pytest.mark.unit
def test_custom_phrase_rendering_and_validation():
    player = TGUser(tg_id=1, username="alice", first_name="Alice")
    assert render_custom_victory_phrase(player, "победа <3", "start") == "@alice — победа &lt;3"
    assert render_custom_victory_phrase(player, "победа", "end") == "победа — @alice"
    assert validate_custom_phrase(" готово ") == "готово"
    with pytest.raises(ValueError, match="multiline"):
        validate_custom_phrase("первая\nвторая")


@pytest.mark.unit
def test_telegram_title_validation():
    assert validate_telegram_title(" Главный ") == "Главный"
    with pytest.raises(ValueError, match="too_long"):
        validate_telegram_title("x" * 17)
    with pytest.raises(ValueError, match="emoji"):
        validate_telegram_title("Главный 🐸")
