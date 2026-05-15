"""Тесты бонуса именинника."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.app.models import TGUser
from bot.handlers.game.commands import _parse_birthday, pidorbirthday_cmd
from bot.handlers.game.game_effects_service import (
    build_selection_pool, is_player_birthday
)
from bot.handlers.game.selection_service import select_winner_with_effects


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


# ─── pidorbirthday_cmd (integration) ─────────────────────────────────

@pytest.fixture
def _bday_update():
    """Mock update с настроенным effective_message.reply_text."""
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 987654321
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.message = MagicMock()
    update.message.text = "/pidorbirthday"
    return update


@pytest.fixture
def _bday_context():
    """Mock context с tg_user и моком db_session."""
    ctx = MagicMock()
    ctx.db_session = MagicMock()
    ctx.db_session.add = MagicMock()
    ctx.db_session.commit = MagicMock()
    user = TGUser(id=1, tg_id=100, first_name='Test', username='testuser',
                  birth_month=None, birth_day=None)
    ctx.tg_user = user
    return ctx


def _mock_config(mocker, enabled=True, multiplier=4):
    """Подменяет get_config для команды."""
    cfg = MagicMock()
    cfg.constants.birthday_enabled = enabled
    cfg.constants.birthday_bonus_multiplier = multiplier
    mocker.patch('bot.handlers.game.commands.get_config', return_value=cfg)
    return cfg


@pytest.mark.asyncio
@pytest.mark.unit
async def test_birthday_cmd_set_valid(_bday_update, _bday_context, mocker):
    _mock_config(mocker)
    _bday_update.message.text = "/pidorbirthday 15.03"

    await pidorbirthday_cmd(_bday_update, _bday_context)

    assert _bday_context.tg_user.birth_month == 3
    assert _bday_context.tg_user.birth_day == 15
    _bday_context.db_session.commit.assert_called_once()
    reply = _bday_update.effective_message.reply_text.await_args[0][0]
    assert '15.03' in reply
    assert 'x4' in reply


@pytest.mark.asyncio
@pytest.mark.unit
async def test_birthday_cmd_clear(_bday_update, _bday_context, mocker):
    _mock_config(mocker)
    _bday_context.tg_user.birth_month = 3
    _bday_context.tg_user.birth_day = 15
    _bday_update.message.text = "/pidorbirthday clear"

    await pidorbirthday_cmd(_bday_update, _bday_context)

    assert _bday_context.tg_user.birth_month is None
    assert _bday_context.tg_user.birth_day is None
    _bday_context.db_session.commit.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_birthday_cmd_invalid_date(_bday_update, _bday_context, mocker):
    _mock_config(mocker)
    _bday_update.message.text = "/pidorbirthday 31.02"  # такого дня нет

    await pidorbirthday_cmd(_bday_update, _bday_context)

    # Юзер не обновился, commit не вызван
    assert _bday_context.tg_user.birth_month is None
    assert _bday_context.tg_user.birth_day is None
    _bday_context.db_session.commit.assert_not_called()
    reply = _bday_update.effective_message.reply_text.await_args[0][0]
    assert 'не понял' in reply.lower() or 'формат' in reply.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_birthday_cmd_info_when_unset(_bday_update, _bday_context, mocker):
    _mock_config(mocker)
    _bday_update.message.text = "/pidorbirthday"

    await pidorbirthday_cmd(_bday_update, _bday_context)

    _bday_context.db_session.commit.assert_not_called()
    reply = _bday_update.effective_message.reply_text.await_args[0][0]
    assert 'не установлен' in reply.lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_birthday_cmd_info_when_set(_bday_update, _bday_context, mocker):
    _mock_config(mocker)
    _bday_context.tg_user.birth_month = 7
    _bday_context.tg_user.birth_day = 4
    _bday_update.message.text = "/pidorbirthday"

    await pidorbirthday_cmd(_bday_update, _bday_context)

    _bday_context.db_session.commit.assert_not_called()
    reply = _bday_update.effective_message.reply_text.await_args[0][0]
    assert '04.07' in reply


@pytest.mark.asyncio
@pytest.mark.unit
async def test_birthday_cmd_disabled_via_config(_bday_update, _bday_context, mocker):
    _mock_config(mocker, enabled=False)
    _bday_update.message.text = "/pidorbirthday 15.03"

    await pidorbirthday_cmd(_bday_update, _bday_context)

    # Фича отключена — никаких изменений
    assert _bday_context.tg_user.birth_month is None
    _bday_context.db_session.commit.assert_not_called()
    reply = _bday_update.effective_message.reply_text.await_args[0][0]
    assert 'выключен' in reply.lower() or 'отключ' in reply.lower()


# ─── Множественные именинники + immunity-reroll ───────────────────────

@pytest.mark.unit
def test_pool_multiple_birthday_players(mock_db_session):
    """Несколько именинников в один день — все получают бонус."""
    _mock_no_double_chance(mock_db_session)
    bd1 = _player(1, month=5, day=13)
    bd2 = _player(2, month=5, day=13)
    other = _player(3)

    pool, _dc, bd = build_selection_pool(
        mock_db_session, 1, [bd1, bd2, other],
        date(2026, 5, 13), birthday_multiplier=4,
    )

    assert pool.count(bd1) == 4
    assert pool.count(bd2) == 4
    assert pool.count(other) == 1
    assert {bd1.id, bd2.id} == bd
    assert other.id not in bd


@pytest.mark.unit
def test_select_winner_immunity_reroll_drops_birthday_bonus(mock_db_session, mocker):
    """Когда именинник защищён и происходит reroll на обычного игрока,
    had_birthday_bonus у итогового победителя должен быть False."""
    # Patch filter_protected_players: именинник защищён
    birthday_player = _player(1, month=5, day=13)
    regular = _player(2)

    mocker.patch(
        'bot.handlers.game.selection_service.filter_protected_players',
        return_value=([regular], [birthday_player]),
    )
    # build_selection_pool делаем стабильным — defer to real function
    _mock_no_double_chance(mock_db_session)
    # random.choice пусть всегда выбирает первого из пула, чтобы попасть на именинника
    mocker.patch(
        'bot.handlers.game.selection_service.random.choice',
        side_effect=lambda lst: lst[0],
    )
    # И защита у именинника срабатывает
    mocker.patch(
        'bot.handlers.game.selection_service.check_winner_immunity',
        return_value=999,  # buyer_id
    )

    result = select_winner_with_effects(
        mock_db_session, game_id=1, players=[birthday_player, regular],
        current_date=date(2026, 5, 13), immunity_enabled=True,
        birthday_multiplier=4,
    )

    # Итоговый победитель — regular (reroll), у него нет ДР
    assert result.winner.id == regular.id
    assert result.had_immunity is True
    assert result.had_birthday_bonus is False
    # Но в birthday_players именинник всё равно отмечен (для анонса)
    assert birthday_player in result.birthday_players
