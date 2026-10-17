"""Persistent opening times for daily draws; calendar days stay Moscow-based."""

import math
import random
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; stored naive values represent UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def choose_next_draw_at(now: datetime) -> datetime:
    tomorrow = now.astimezone(MOSCOW_TZ).date() + timedelta(days=1)
    hour = random.randint(0, 18)
    return datetime.combine(tomorrow, time(hour), tzinfo=MOSCOW_TZ).astimezone(timezone.utc)


def format_next_draw(next_draw_at: datetime) -> str:
    local = as_utc(next_draw_at).astimezone(MOSCOW_TZ)
    return f"🕒 Следующий розыгрыш доступен {local:%d.%m.%Y} с {local:%H:%M} МСК."


def format_draw_locked(next_draw_at: datetime, now: datetime) -> str:
    minutes = math.ceil((as_utc(next_draw_at) - as_utc(now)).total_seconds() / 60)
    hours, minutes = divmod(max(0, minutes), 60)
    return f"Рано! {format_next_draw(next_draw_at)} Осталось {hours} ч {minutes} мин."
