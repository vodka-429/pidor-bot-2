"""
Общие фикстуры для тестирования игровых команд
"""
import pytest
from unittest.mock import MagicMock, Mock, AsyncMock
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
    update.effective_chat.send_message = AsyncMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_markdown_v2 = AsyncMock()
    update.message = MagicMock()
    update.message.reply_markdown_v2 = AsyncMock()
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
    # Инициализируем bot_data для поддержки chat_whitelist проверки
    context.bot_data = {'chat_whitelist': None}  # None = нет ограничений (все чаты разрешены)
    # Мокируем bot с async методами
    context.bot = MagicMock()
    context.bot.send_message = AsyncMock()
    context.bot.get_chat_member = AsyncMock()
    return context


@pytest.fixture
def sample_players():
    """Список тестовых игроков"""
    from bot.app.models import TGUser
    players = []
    for i in range(1, 4):
        # Создаём реальные объекты TGUser вместо MagicMock
        # чтобы full_username() возвращал строку
        player = TGUser(
            id=i,
            tg_id=100000000 + i,
            username=f"player{i}",
            first_name="Player",
            last_name=f"Number{i}"
        )
        players.append(player)
    return players


@pytest.fixture(autouse=True)
def mock_shop_effects(request, mocker):
    """Автоматически мокирует get_or_create_player_effects для всех тестов, кроме test_shop_service.py и test_shop_integration.py и test_game_effects_service.py"""
    # Пропускаем автоматический мок для тестов, которые тестируют эту функцию или требуют кастомных моков
    skip_tests = ['test_shop_service', 'test_shop_integration', 'test_game_effects_service']
    if any(test_name in request.node.nodeid for test_name in skip_tests):
        return None

    mock_effect = MagicMock()
    mock_effect.immunity_until = None
    mock_effect.double_chance_until = None
    # Патчим в обоих местах - в shop_service и в game_effects_service
    mocker.patch('bot.handlers.game.shop_service.get_or_create_player_effects', return_value=mock_effect)
    mocker.patch('bot.handlers.game.game_effects_service.get_or_create_player_effects', return_value=mock_effect)
    return mock_effect
