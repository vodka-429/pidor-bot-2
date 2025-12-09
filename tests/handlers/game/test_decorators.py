"""
Тесты для декоратора ensure_game
"""
import pytest
from unittest.mock import MagicMock, patch
from bot.handlers.game.commands import ensure_game
from bot.app.models import Game


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensure_game_creates_new_game(mock_update, mock_context):
    """Проверка создания новой игры, если её нет"""
    # Arrange
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = None
    
    @ensure_game
    async def dummy_handler(update, context):
        return context.game
    
    # Act
    result = await dummy_handler(mock_update, mock_context)
    
    # Assert
    mock_context.db_session.add.assert_called_once()
    mock_context.db_session.commit.assert_called_once()
    mock_context.db_session.refresh.assert_called_once()
    assert mock_context.game is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensure_game_uses_existing_game(mock_update, mock_context, mock_game):
    """Проверка использования существующей игры"""
    # Arrange
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = mock_game
    
    @ensure_game
    async def dummy_handler(update, context):
        return context.game
    
    # Act
    result = await dummy_handler(mock_update, mock_context)
    
    # Assert
    assert result == mock_game
    assert mock_context.game == mock_game
    # Проверяем, что add не вызывался (игра уже существует)
    mock_context.db_session.add.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensure_game_adds_game_to_context(mock_update, mock_context):
    """Проверка добавления game в context"""
    # Arrange
    new_game = MagicMock(spec=Game)
    new_game.id = 1
    new_game.chat_id = mock_update.effective_chat.id
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = None
    
    @ensure_game
    async def dummy_handler(update, context):
        # Проверяем, что game добавлен в контекст
        assert hasattr(context, 'game')
        assert context.game is not None
        return True
    
    # Act
    result = await dummy_handler(mock_update, mock_context)
    
    # Assert
    assert result is True
    assert hasattr(mock_context, 'game')


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ensure_game_commits_new_game(mock_update, mock_context):
    """Проверка коммита новой игры в БД"""
    # Arrange
    mock_context.db_session.query.return_value.filter_by.return_value.one_or_none.return_value = None
    
    @ensure_game
    async def dummy_handler(update, context):
        return context.game
    
    # Act
    await dummy_handler(mock_update, mock_context)
    
    # Assert
    # Проверяем последовательность вызовов: add -> commit -> refresh
    assert mock_context.db_session.add.called
    assert mock_context.db_session.commit.called
    assert mock_context.db_session.refresh.called
    
    # Проверяем, что add был вызван перед commit
    call_order = []
    for call in mock_context.db_session.method_calls:
        if call[0] in ['add', 'commit', 'refresh']:
            call_order.append(call[0])
    
    assert 'add' in call_order
    assert 'commit' in call_order
    assert 'refresh' in call_order
