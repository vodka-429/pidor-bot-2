"""
Общие фикстуры для тестирования игровых команд
"""
import pytest
from unittest.mock import MagicMock, Mock
from datetime import datetime


@pytest.fixture
def mock_db_session():
    """Мок сессии БД с основными методами"""
    session = MagicMock()
    session.query = MagicMock(return_value=session)
    session.filter_by = MagicMock(return_value=session)
    session.one_or_none = MagicMock(return_value=None)
    session.add = MagicMock()
    session.commit = MagicMock()
    session.refresh = MagicMock()
    session.exec = MagicMock(return_value=session)
    session.all = MagicMock(return_value=[])
    session.one = MagicMock()
    return session


@pytest.fixture
def mock_tg_user():
    """Мок пользователя Telegram"""
    user = MagicMock()
    user.id = 1
    user.tg_id = 123456789
    user.username = "testuser"
    user.first_name = "Test"
    user.last_name = "User"
    user.full_username = MagicMock(return_value="@testuser")
    return user


@pytest.fixture
def mock_game(mock_db_session):
    """Мок объекта Game"""
    game = MagicMock()
    game.id = 1
    game.chat_id = 987654321
    game.players = []
    game.results = MagicMock()
    game.results.append = MagicMock()
    return game


@pytest.fixture
def mock_update():
    """Мок объекта Update от telegram"""
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 987654321
    update.effective_chat.send_message = MagicMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_markdown_v2 = MagicMock()
    update.message = MagicMock()
    update.message.reply_markdown_v2 = MagicMock()
    update.message.from_user = MagicMock()
    update.message.from_user.name = "TestUser"
    update.message.text = "/pidor"
    return update


@pytest.fixture
def mock_context(mock_db_session, mock_tg_user):
    """Мок контекста с db_session и tg_user"""
    context = MagicMock()
    context.db_session = mock_db_session
    context.tg_user = mock_tg_user
    context.game = None
    return context


@pytest.fixture
def sample_players():
    """Список тестовых игроков"""
    players = []
    for i in range(1, 4):
        player = MagicMock()
        player.id = i
        player.tg_id = 100000000 + i
        player.username = f"player{i}"
        player.first_name = f"Player"
        player.last_name = f"Number{i}"
        player.full_username = MagicMock(return_value=f"@player{i}")
        players.append(player)
    return players