"""Тесты бонуса именинника."""
from datetime import date
from unittest.mock import MagicMock

import pytest

from bot.app.models import TGUser
from bot.handlers.game.commands import _parse_birthday
from bot.handlers.game.game_effects_service import (
    build_selection_pool, is_player_birthday
)


def _player(uid: int, month=None, day=None) -> TGUser:
    return TGUser(
        id=uid, tg_id=100 + uid, first_name=f"P{uid}", username=f"p{uid}",
        birth_month=month, birth_day=day,
    )


def _mock_no_double_chance(mock_db_session):
    """Заглушка: нет активных покупок double_chance."""
    result = MagicMock()
    result.all.return_value = []
    mock_db_session.exec.return_value = result


# ─── is_player_birthday ──────────────────────────────────────────────

@pytest.mark.unit
def test_is_player_birthday_matches():
    p = _player(1, month=5, day=13)
    assert is_player_birthday(p, date(2026, 5, 13)) is True


@pytest.mark.unit
def test_is_player_birthday_different_day():
    p = _player(1, month=5, day=13)
    assert is_player_birthday(p, date(2026, 5, 14)) is False


@pytest.mark.unit
def test_is_player_birthday_no_data():
    p = _player(1, month=None, day=None)
    assert is_player_birthday(p, date(2026, 5, 13)) is False


@pytest.mark.unit
def test_is_player_birthday_feb_29_in_leap_year():
    p = _player(1, month=2, day=29)
    assert is_player_birthday(p, date(2024, 2, 29)) is True


@pytest.mark.unit
def test_is_player_birthday_feb_29_in_non_leap_year_celebrates_on_28():
    p = _player(1, month=2, day=29)
    # 2026 не високосный → отмечаем 28.02
    assert is_player_birthday(p, date(2026, 2, 28)) is True
    assert is_player_birthday(p, date(2026, 3, 1)) is False


@pytest.mark.unit
def test_is_player_birthday_feb_28_not_affected_by_feb_29_logic():
    # Обычный игрок с ДР 28.02 не должен срабатывать дважды
    p = _player(1, month=2, day=28)
    assert is_player_birthday(p, date(2026, 2, 28)) is True
    # Игрок с ДР 28.02 — на 28.02 совпадение по точному условию


# ─── build_selection_pool: birthday bonus ────────────────────────────

@pytest.mark.unit
def test_pool_birthday_x4_multiplier(mock_db_session):
    _mock_no_double_chance(mock_db_session)
    birthday_player = _player(1, month=5, day=13)
    other = _player(2)

    pool, dc, bd = build_selection_pool(
        mock_db_session, 1, [birthday_player, other],
        date(2026, 5, 13), birthday_multiplier=4,
    )

    assert pool.count(birthday_player) == 4
    assert pool.count(other) == 1
    assert birthday_player.id in bd
    assert other.id not in bd
    assert birthday_player.id not in dc


@pytest.mark.unit
def test_pool_birthday_disabled_when_multiplier_is_1(mock_db_session):
    _mock_no_double_chance(mock_db_session)
    birthday_player = _player(1, month=5, day=13)
    other = _player(2)

    pool, _dc, bd = build_selection_pool(
        mock_db_session, 1, [birthday_player, other],
        date(2026, 5, 13), birthday_multiplier=1,
    )

    # multiplier=1 → фича отключена, никаких бонусов
    assert pool.count(birthday_player) == 1
    assert pool.count(other) == 1
    assert len(bd) == 0


@pytest.mark.unit
def test_pool_birthday_combines_with_double_chance(mock_db_session):
    """Именинник + 1 покупка double_chance: 2 * 4 = 8 записей."""
    from bot.app.models import DoubleChancePurchase

    birthday_player = _player(1, month=5, day=13)
    other = _player(2)

    purchase = DoubleChancePurchase(
        game_id=1, buyer_id=99, target_id=birthday_player.id,
        year=2026, day=date(2026, 5, 13).timetuple().tm_yday, is_used=False,
    )
    result = MagicMock()
    result.all.return_value = [purchase]
    mock_db_session.exec.return_value = result

    pool, dc, bd = build_selection_pool(
        mock_db_session, 1, [birthday_player, other],
        date(2026, 5, 13), birthday_multiplier=4,
    )

    assert pool.count(birthday_player) == 8  # 2 ** 1 * 4
    assert pool.count(other) == 1
    assert birthday_player.id in dc
    assert birthday_player.id in bd


@pytest.mark.unit
def test_pool_no_birthdays_today(mock_db_session):
    _mock_no_double_chance(mock_db_session)
    p1 = _player(1, month=12, day=31)
    p2 = _player(2)

    pool, _dc, bd = build_selection_pool(
        mock_db_session, 1, [p1, p2],
        date(2026, 5, 13), birthday_multiplier=4,
    )

    assert pool.count(p1) == 1
    assert pool.count(p2) == 1
    assert len(bd) == 0


# ─── _parse_birthday ─────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("text,expected", [
    ("15.03", (3, 15)),
    ("05.12", (12, 5)),
    ("1.1", (1, 1)),
    ("29.02", (2, 29)),   # допускаем 29.02 — год учитывается в логике розыгрыша
    ("31.12", (12, 31)),
    ("15-03", (3, 15)),    # через дефис
    ("15/03", (3, 15)),    # через слэш
])
def test_parse_birthday_valid(text, expected):
    assert _parse_birthday(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "",
    "abc",
    "15",
    "15.03.2024",
    "32.01",
    "15.13",
    "0.5",
    "5.0",
    "31.04",  # апрель — 30 дней
    "31.02",
    "-1.5",
])
def test_parse_birthday_invalid(text):
    assert _parse_birthday(text) is None
