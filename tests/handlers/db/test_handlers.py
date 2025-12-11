"""Tests for database handlers functionality."""
import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy.exc import DisconnectionError, OperationalError

from bot.handlers.db.handlers import retry_on_db_error, tg_user_middleware_handler


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_on_db_error_success_first_attempt():
    """Test retry decorator succeeds on first attempt."""
    
    @retry_on_db_error(max_retries=3, delay=0.1, backoff=2)
    async def test_function():
        return "success"
    
    result = await test_function()
    assert result == "success"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_on_db_error_success_after_retries():
    """Test retry decorator succeeds after some retries."""
    call_count = 0
    
    @retry_on_db_error(max_retries=3, delay=0.01, backoff=2)
    async def test_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise DisconnectionError("Connection lost", None, None)
        return "success"
    
    result = await test_function()
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_on_db_error_max_retries_exceeded():
    """Test retry decorator fails after max retries exceeded."""
    call_count = 0
    
    @retry_on_db_error(max_retries=2, delay=0.01, backoff=2)
    async def test_function():
        nonlocal call_count
        call_count += 1
        raise OperationalError("Database error", None, None)
    
    with pytest.raises(OperationalError):
        await test_function()
    
    assert call_count == 2  # Should try max_retries times


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_on_db_error_non_db_error_no_retry():
    """Test retry decorator doesn't retry for non-DB errors."""
    call_count = 0
    
    @retry_on_db_error(max_retries=3, delay=0.01, backoff=2)
    async def test_function():
        nonlocal call_count
        call_count += 1
        raise ValueError("Not a DB error")
    
    with pytest.raises(ValueError):
        await test_function()
    
    assert call_count == 1  # Should not retry for non-DB errors


@pytest.mark.asyncio
@pytest.mark.unit
async def test_retry_on_db_error_exponential_backoff():
    """Test retry decorator uses exponential backoff."""
    call_times = []
    
    @retry_on_db_error(max_retries=3, delay=0.1, backoff=2)
    async def test_function():
        call_times.append(time.time())
        if len(call_times) < 3:
            raise DisconnectionError("Connection lost", None, None)
        return "success"
    
    start_time = time.time()
    result = await test_function()
    
    assert result == "success"
    assert len(call_times) == 3
    
    # Check that delays increase exponentially (approximately)
    # First retry: ~0.1s, Second retry: ~0.2s
    if len(call_times) >= 3:
        delay1 = call_times[1] - call_times[0]
        delay2 = call_times[2] - call_times[1]
        
        # Allow some tolerance for timing variations
        assert delay1 >= 0.08  # Should be around 0.1s
        assert delay2 >= 0.18  # Should be around 0.2s
        assert delay2 > delay1  # Second delay should be longer


@pytest.mark.asyncio
@pytest.mark.unit
async def test_tg_user_middleware_handler_with_retry():
    """Test tg_user_middleware_handler has retry decorator applied."""
    # Setup mock update and context
    mock_update = MagicMock()
    mock_update.effective_user.id = 123
    mock_update.effective_user.username = "testuser"
    mock_update.effective_user.first_name = "Test"
    mock_update.effective_user.last_name = "User"
    mock_update.effective_user.language_code = "en"
    mock_update.message = MagicMock()  # Has message (not callback)
    
    mock_context = MagicMock()
    mock_session = MagicMock()
    mock_context.db_session = mock_session
    
    # Setup mock query to return None (new user)
    mock_session.query.return_value.filter_by.return_value.one_or_none.return_value = None
    
    # Test that function works normally
    await tg_user_middleware_handler(mock_update, mock_context)
    
    # Verify session operations were called
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_tg_user_middleware_handler_retry_on_db_error():
    """Test tg_user_middleware_handler retries on database errors."""
    # Setup mock update and context
    mock_update = MagicMock()
    mock_update.effective_user.id = 123
    mock_update.effective_user.username = "testuser"
    mock_update.effective_user.first_name = "Test"
    mock_update.effective_user.last_name = "User"
    mock_update.effective_user.language_code = "en"
    mock_update.message = MagicMock()
    
    mock_context = MagicMock()
    mock_session = MagicMock()
    mock_context.db_session = mock_session
    
    # Setup mock query to return None (new user)
    mock_session.query.return_value.filter_by.return_value.one_or_none.return_value = None
    
    # Make commit fail first time, then succeed
    call_count = 0
    def commit_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise DisconnectionError("Connection lost", None, None)
        return None
    
    mock_session.commit.side_effect = commit_side_effect
    
    # Execute - should succeed after retry
    await tg_user_middleware_handler(mock_update, mock_context)
    
    # Verify commit was called twice (failed once, succeeded once)
    assert mock_session.commit.call_count == 2
    assert call_count == 2
