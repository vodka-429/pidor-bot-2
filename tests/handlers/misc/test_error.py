"""Tests for error handler."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from bot.handlers.misc.error import bot_error_handler


@pytest.mark.asyncio
@pytest.mark.unit
async def test_error_handler_with_none_update():
    """Test that error handler doesn't crash when update is None."""
    # Setup
    context = MagicMock()
    context.error = Exception("Test error")

    # Execute - should not raise exception
    with patch('bot.handlers.misc.error.logger') as mock_logger:
        await bot_error_handler(None, context)

        # Verify that error was logged
        assert mock_logger.error.call_count >= 1

        # Verify that specific log about None update was made
        calls = [str(call) for call in mock_logger.error.call_args_list]
        assert any("update or effective_chat is None" in call for call in calls)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_error_handler_with_none_chat():
    """Test that error handler doesn't crash when update.effective_chat is None."""
    # Setup
    update = MagicMock()
    update.effective_chat = None
    update.effective_user = MagicMock()
    update.effective_user.id = 12345

    context = MagicMock()
    context.error = Exception("Test error")

    # Execute - should not raise exception
    with patch('bot.handlers.misc.error.logger') as mock_logger:
        await bot_error_handler(update, context)

        # Verify that error was logged
        assert mock_logger.error.call_count >= 1

        # Verify that specific log about None chat was made
        calls = [str(call) for call in mock_logger.error.call_args_list]
        assert any("update or effective_chat is None" in call for call in calls)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_error_handler_logs_error():
    """Test that error handler logs error information correctly."""
    # Setup
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 987654321
    update.effective_chat.send_message = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 12345

    context = MagicMock()
    test_error = ValueError("Test error message")
    context.error = test_error

    # Execute
    with patch('bot.handlers.misc.error.logger') as mock_logger:
        await bot_error_handler(update, context)

        # Verify that error was logged with correct information
        assert mock_logger.error.call_count >= 1

        # Check that error details were logged
        first_call = mock_logger.error.call_args_list[0]
        log_message = str(first_call)

        assert "ValueError" in log_message
        assert "Test error message" in log_message
        assert "987654321" in log_message  # chat_id
        assert "12345" in log_message  # user_id


@pytest.mark.asyncio
@pytest.mark.unit
async def test_error_handler_no_recursion():
    """Test that error handler doesn't recurse when send_message fails."""
    # Setup
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 987654321
    # Make send_message raise an exception
    update.effective_chat.send_message = AsyncMock(side_effect=Exception("Send failed"))
    update.effective_user = MagicMock()
    update.effective_user.id = 12345

    context = MagicMock()
    context.error = Exception("Original error")

    # Execute - should not raise exception and should not recurse
    with patch('bot.handlers.misc.error.logger') as mock_logger:
        await bot_error_handler(update, context)

        # Verify that both errors were logged
        assert mock_logger.error.call_count >= 2

        # Check that send failure was logged
        calls = [str(call) for call in mock_logger.error.call_args_list]
        assert any("Failed to send error message" in call for call in calls)

        # Verify send_message was called only once (no recursion)
        assert update.effective_chat.send_message.call_count == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_error_handler_sends_message_to_user():
    """Test that error handler sends error message to user when possible."""
    # Setup
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 987654321
    update.effective_chat.send_message = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 12345

    context = MagicMock()
    context.error = Exception("Test error")

    # Execute
    with patch('bot.handlers.misc.error.logger'):
        await bot_error_handler(update, context)

        # Verify that send_message was called
        update.effective_chat.send_message.assert_called_once()

        # Verify the message content
        call_args = update.effective_chat.send_message.call_args
        assert 'An error occurred while processing the update.' in str(call_args)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_error_handler_with_none_effective_user():
    """Test that error handler works when effective_user is None."""
    # Setup
    update = MagicMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 987654321
    update.effective_chat.send_message = AsyncMock()
    update.effective_user = None

    context = MagicMock()
    context.error = Exception("Test error")

    # Execute - should not raise exception
    with patch('bot.handlers.misc.error.logger') as mock_logger:
        await bot_error_handler(update, context)

        # Verify that error was logged
        assert mock_logger.error.call_count >= 1

        # Verify that message was sent despite None user
        update.effective_chat.send_message.assert_called_once()
