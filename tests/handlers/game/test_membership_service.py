"""Unit tests for membership_service."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from bot.app.models import GamePlayer, TGUser
from bot.handlers.game.membership_service import (
    get_active_players,
    get_deactivated_player_ids,
    deactivate_player,
    reactivate_player,
    check_player_membership,
    batch_check_membership,
)


@pytest.fixture
def db():
    """Мок сессии БД."""
    session = MagicMock()
    session.exec = MagicMock(return_value=session)
    session.all = MagicMock(return_value=[])
    session.first = MagicMock(return_value=None)
    session.add = MagicMock()
    session.commit = MagicMock()
    return session


@pytest.fixture
def make_player():
    def _make(user_id, tg_id=None, is_active=True, game_id=1):
        player = TGUser(id=user_id, tg_id=tg_id or (100000 + user_id),
                        first_name=f"Player{user_id}")
        gp = MagicMock(spec=GamePlayer)
        gp.user_id = user_id
        gp.game_id = game_id
        gp.is_active = is_active
        return player, gp
    return _make


@pytest.mark.unit
class TestGetActivePlayers:
    def test_returns_result_of_exec(self, db, make_player):
        player1, _ = make_player(1)
        player2, _ = make_player(2)
        db.exec.return_value.all.return_value = [player1, player2]

        result = get_active_players(db, game_id=1)

        assert result == [player1, player2]
        db.exec.assert_called_once()

    def test_returns_empty_when_no_active(self, db):
        db.exec.return_value.all.return_value = []

        result = get_active_players(db, game_id=1)

        assert result == []


@pytest.mark.unit
class TestGetDeactivatedPlayerIds:
    def test_returns_set_of_user_ids(self, db):
        db.exec.return_value.all.return_value = [2, 5]

        result = get_deactivated_player_ids(db, game_id=1)

        assert result == {2, 5}

    def test_returns_empty_set_when_none(self, db):
        db.exec.return_value.all.return_value = []

        result = get_deactivated_player_ids(db, game_id=1)

        assert result == set()


@pytest.mark.unit
class TestDeactivatePlayer:
    def test_deactivates_active_player(self, db, make_player):
        _, gp = make_player(1, is_active=True)
        db.exec.return_value.first.return_value = gp

        deactivate_player(db, game_id=1, user_id=1)

        assert gp.is_active is False
        db.add.assert_called_once_with(gp)
        db.commit.assert_called_once()

    def test_skips_already_inactive_player(self, db, make_player):
        _, gp = make_player(1, is_active=False)
        db.exec.return_value.first.return_value = gp

        deactivate_player(db, game_id=1, user_id=1)

        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_skips_if_player_not_found(self, db):
        db.exec.return_value.first.return_value = None

        deactivate_player(db, game_id=1, user_id=99)

        db.add.assert_not_called()
        db.commit.assert_not_called()


@pytest.mark.unit
class TestReactivatePlayer:
    def test_reactivates_inactive_player(self, db, make_player):
        _, gp = make_player(1, is_active=False)
        db.exec.return_value.first.return_value = gp

        reactivate_player(db, game_id=1, user_id=1)

        assert gp.is_active is True
        db.add.assert_called_once_with(gp)
        db.commit.assert_called_once()

    def test_skips_already_active_player(self, db, make_player):
        _, gp = make_player(1, is_active=True)
        db.exec.return_value.first.return_value = gp

        reactivate_player(db, game_id=1, user_id=1)

        db.add.assert_not_called()

    def test_skips_if_player_not_found(self, db):
        db.exec.return_value.first.return_value = None

        reactivate_player(db, game_id=1, user_id=99)

        db.add.assert_not_called()


@pytest.mark.unit
class TestCheckPlayerMembership:
    @pytest.mark.asyncio
    async def test_deactivates_left_user(self, db, make_player):
        bot = MagicMock()
        member = MagicMock()
        member.status = 'left'
        bot.get_chat_member = AsyncMock(return_value=member)

        player, gp = make_player(1)
        db.exec.return_value.first.return_value = gp

        await check_player_membership(bot, chat_id=100, db_session=db, game_id=1, player=player)

        assert gp.is_active is False

    @pytest.mark.asyncio
    async def test_deactivates_kicked_user(self, db, make_player):
        bot = MagicMock()
        member = MagicMock()
        member.status = 'kicked'
        bot.get_chat_member = AsyncMock(return_value=member)

        player, gp = make_player(1)
        db.exec.return_value.first.return_value = gp

        await check_player_membership(bot, chat_id=100, db_session=db, game_id=1, player=player)

        assert gp.is_active is False

    @pytest.mark.asyncio
    async def test_keeps_active_member(self, db, make_player):
        bot = MagicMock()
        member = MagicMock()
        member.status = 'member'
        bot.get_chat_member = AsyncMock(return_value=member)

        player, gp = make_player(1, is_active=True)
        db.exec.return_value.first.return_value = gp

        await check_player_membership(bot, chat_id=100, db_session=db, game_id=1, player=player)

        assert gp.is_active is True
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_safe_default_on_api_error(self, db, make_player):
        """При ошибке API пользователь остаётся активным."""
        bot = MagicMock()
        bot.get_chat_member = AsyncMock(side_effect=Exception("API error"))

        player, gp = make_player(1, is_active=True)
        db.exec.return_value.first.return_value = gp

        await check_player_membership(bot, chat_id=100, db_session=db, game_id=1, player=player)

        # No deactivation on error
        db.add.assert_not_called()
        db.commit.assert_not_called()


@pytest.mark.unit
class TestBatchCheckMembership:
    @pytest.mark.asyncio
    async def test_checks_all_players(self, db, make_player):
        bot = MagicMock()
        member_active = MagicMock()
        member_active.status = 'member'
        member_left = MagicMock()
        member_left.status = 'left'
        bot.get_chat_member = AsyncMock(side_effect=[member_active, member_left])

        player1, gp1 = make_player(1, is_active=True)
        player2, gp2 = make_player(2, is_active=True)

        # Only player2 gets deactivated (left) → only one DB lookup for player2's GamePlayer
        db.exec.return_value.first.return_value = gp2

        await batch_check_membership(bot, chat_id=100, db_session=db, game_id=1,
                                     players=[player1, player2])

        assert bot.get_chat_member.call_count == 2
        assert gp1.is_active is True
        assert gp2.is_active is False

    @pytest.mark.asyncio
    async def test_empty_players_list(self, db):
        bot = MagicMock()
        bot.get_chat_member = AsyncMock()

        await batch_check_membership(bot, chat_id=100, db_session=db, game_id=1, players=[])

        bot.get_chat_member.assert_not_called()
