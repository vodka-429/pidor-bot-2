import logging

from telegram import Update
from telegram.ext import CallbackContext

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


def bot_error_handler(update: Update, context: CallbackContext) -> None:
    """
    Handle errors that occur during update processing.

    This handler includes protection against recursive calls and handles cases
    where update or chat information might be None.
    """
    # Log detailed error information
    error_type = type(context.error).__name__
    error_msg = str(context.error)

    # Extract chat and user info if available
    chat_id = update.effective_chat.id if update and update.effective_chat else None
    user_id = update.effective_user.id if update and update.effective_user else None

    logger.error(
        f"Exception while handling an update. "
        f"Error type: {error_type}, "
        f"Error message: {error_msg}, "
        f"Chat ID: {chat_id}, "
        f"User ID: {user_id}",
        exc_info=context.error
    )

    # Check if update and chat are available before trying to send message
    if update is None or update.effective_chat is None:
        logger.error("Cannot send error message to user: update or effective_chat is None")
        return

    # Try to send error message to user, but catch any exceptions to prevent recursion
    try:
        update.effective_chat.send_message('An error occurred while processing the update.')
    except Exception as send_error:
        # Log the error but don't try to send another message (prevent recursion)
        logger.error(
            f"Failed to send error message to chat {chat_id}: {type(send_error).__name__}: {send_error}"
        )
