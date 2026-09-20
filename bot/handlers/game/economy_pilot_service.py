"""Services for pilot coin sinks: rain, victory phrases and Telegram titles."""
import json
import random
from datetime import datetime
from html import escape as html_escape
from typing import Iterable, Optional

from sqlalchemy import func
from sqlmodel import select

from bot.app.models import (
    ChatBank,
    CoinRainPurchase,
    Game,
    GamePlayer,
    TGUser,
)
from bot.handlers.game.coin_service import add_coins
from bot.handlers.game.config import get_config_by_game_id
from bot.handlers.game.shop_service import process_purchase, spend_coins, can_afford
from bot.handlers.game.transfer_service import get_or_create_chat_bank


CUSTOM_PHRASE_MAX_LENGTH = 120
TELEGRAM_TITLE_MAX_LENGTH = 16


def get_game_player(db_session, game_id: int, user_id: int) -> Optional[GamePlayer]:
    return db_session.exec(
        select(GamePlayer).where(
            GamePlayer.game_id == game_id,
            GamePlayer.user_id == user_id,
        )
    ).first()


def validate_custom_phrase(value: str) -> str:
    phrase = value.strip()
    if not phrase:
        raise ValueError("empty")
    if "\n" in phrase or "\r" in phrase:
        raise ValueError("multiline")
    if len(phrase) > CUSTOM_PHRASE_MAX_LENGTH:
        raise ValueError("too_long")
    return phrase


def render_custom_victory_phrase(player: TGUser, phrase: str, position: str) -> str:
    name = html_escape(player.full_username(mention=True))
    safe_phrase = html_escape(phrase)
    if position == "end":
        return f"{safe_phrase} — {name}"
    return f"{name} — {safe_phrase}"


def get_custom_victory_message(db_session, game_id: int, player: TGUser) -> Optional[str]:
    link = get_game_player(db_session, game_id, player.id)
    if (
        link is None
        or not isinstance(link.custom_victory_phrase, str)
        or not link.custom_victory_phrase
    ):
        return None
    return render_custom_victory_phrase(
        player,
        link.custom_victory_phrase,
        link.custom_victory_name_position or "start",
    )


def buy_custom_victory_phrase(
    db_session,
    game_id: int,
    user_id: int,
    phrase: str,
    position: str,
    year: int,
    auto_commit: bool = True,
) -> tuple[bool, str, int]:
    config = get_config_by_game_id(db_session, game_id)
    if not config.constants.custom_phrase_enabled:
        return False, "feature_disabled", 0
    phrase = validate_custom_phrase(phrase)
    if position not in {"start", "end"}:
        raise ValueError("invalid_position")

    link = get_game_player(db_session, game_id, user_id)
    if link is None or not link.is_active:
        return False, "not_registered", 0

    success, error, commission = process_purchase(
        db_session,
        game_id,
        user_id,
        config.constants.custom_phrase_price,
        year,
        "custom_victory_phrase",
    )
    if not success:
        return False, error, 0

    link.custom_victory_phrase = phrase
    link.custom_victory_name_position = position
    db_session.add(link)
    if auto_commit:
        db_session.commit()
    return True, "success", commission


def clear_custom_victory_phrase(db_session, game_id: int, user_id: int) -> bool:
    link = get_game_player(db_session, game_id, user_id)
    if link is None:
        return False
    link.custom_victory_phrase = None
    link.custom_victory_name_position = None
    db_session.add(link)
    db_session.commit()
    return True


def validate_telegram_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise ValueError("empty")
    if "\n" in title or "\r" in title:
        raise ValueError("multiline")
    if len(title) > TELEGRAM_TITLE_MAX_LENGTH:
        raise ValueError("too_long")
    if _contains_emoji(title):
        raise ValueError("emoji")
    return title


def _contains_emoji(value: str) -> bool:
    for char in value:
        point = ord(char)
        if (
            0x1F000 <= point <= 0x1FAFF
            or 0x2600 <= point <= 0x27BF
            or 0x2300 <= point <= 0x23FF
            or point in {0x200D, 0xFE0F, 0x20E3}
        ):
            return True
    return False


def record_telegram_title_purchase(
    db_session,
    game_id: int,
    user_id: int,
    title: str,
    year: int,
    auto_commit: bool = True,
) -> tuple[bool, str, int]:
    config = get_config_by_game_id(db_session, game_id)
    if not config.constants.telegram_title_enabled:
        return False, "feature_disabled", 0
    title = validate_telegram_title(title)
    link = get_game_player(db_session, game_id, user_id)
    if link is None or not link.is_active:
        return False, "not_registered", 0

    success, error, commission = process_purchase(
        db_session,
        game_id,
        user_id,
        config.constants.telegram_title_price,
        year,
        "telegram_title",
    )
    if not success:
        return False, error, 0

    link.telegram_title = title
    db_session.add(link)
    if auto_commit:
        db_session.commit()
    return True, "success", commission


def clear_recorded_telegram_title(
    db_session, game_id: int, user_id: int, auto_commit: bool = True
) -> bool:
    link = get_game_player(db_session, game_id, user_id)
    if link is None:
        return False
    link.telegram_title = None
    db_session.add(link)
    if auto_commit:
        db_session.commit()
    return True


def execute_coin_rain(
    db_session,
    game_id: int,
    buyer_id: int,
    active_players: Iterable[TGUser],
    year: int,
    day: int,
) -> tuple[bool, str, list[TGUser], int]:
    """Buy a rain atomically. Every undistributed coin goes to the chat bank."""
    config = get_config_by_game_id(db_session, game_id)
    c = config.constants
    if not c.coin_rain_enabled:
        return False, "feature_disabled", [], 0

    # Serialise all rain purchases for one chat before checking both limits.
    db_session.exec(select(Game).where(Game.id == game_id).with_for_update()).first()

    buyer_purchase = db_session.exec(
        select(CoinRainPurchase).where(
            CoinRainPurchase.game_id == game_id,
            CoinRainPurchase.buyer_id == buyer_id,
            CoinRainPurchase.year == year,
            CoinRainPurchase.day == day,
        )
    ).first()
    if buyer_purchase is not None:
        return False, "buyer_daily_limit", [], 0

    chat_count = db_session.exec(
        select(func.count(CoinRainPurchase.id)).where(
            CoinRainPurchase.game_id == game_id,
            CoinRainPurchase.year == year,
            CoinRainPurchase.day == day,
        )
    ).one()
    if chat_count >= c.coin_rain_chat_daily_limit:
        return False, "chat_daily_limit", [], 0
    if not can_afford(db_session, game_id, buyer_id, c.coin_rain_price):
        return False, "insufficient_funds", [], 0

    eligible_by_id = {
        player.id: player
        for player in active_players
        if player.id is not None and player.id != buyer_id
    }
    recipient_count = min(c.coin_rain_max_recipients, len(eligible_by_id))
    recipients = random.sample(list(eligible_by_id.values()), recipient_count)
    distributed = recipient_count * c.coin_rain_recipient_amount
    bank_amount = c.coin_rain_price - distributed

    spend_coins(
        db_session, game_id, buyer_id, c.coin_rain_price, year,
        "coin_rain", auto_commit=False,
    )
    for recipient in recipients:
        add_coins(
            db_session, game_id, recipient.id, c.coin_rain_recipient_amount,
            year, "coin_rain_reward", auto_commit=False,
        )

    bank: ChatBank = get_or_create_chat_bank(db_session, game_id, auto_commit=False)
    bank.balance += bank_amount
    bank.updated_at = datetime.utcnow()
    db_session.add(bank)
    db_session.add(CoinRainPurchase(
        game_id=game_id,
        buyer_id=buyer_id,
        year=year,
        day=day,
        price=c.coin_rain_price,
        recipient_amount=c.coin_rain_recipient_amount,
        recipient_ids=json.dumps([player.id for player in recipients]),
        distributed_amount=distributed,
        bank_amount=bank_amount,
    ))
    db_session.commit()
    return True, "success", recipients, bank_amount
