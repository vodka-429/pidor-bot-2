"""Command routing for all active usernames of a bot."""

import logging

from telegram import Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import Application, CommandHandler, filters

from bot.handlers.game.config import get_config


logger = logging.getLogger(__name__)


async def load_bot_username_aliases(application: Application):
    """Discover the bot's active usernames before updates start being processed."""
    bot = application.bot
    try:
        try:
            chat = await bot.get_chat(bot.id)
        except BadRequest:
            # A private chat with the bot itself may not exist in the API cache yet.
            chat = await bot.get_chat(f'@{bot.username}')
    except TelegramError as error:
        logger.warning(
            'Could not discover active bot usernames (%s); using the primary '
            'username and configured bot_username_aliases', type(error).__name__,
        )
        return

    if chat.id != bot.id:
        logger.warning('Ignoring active usernames returned for a different bot ID')
        return

    usernames = frozenset(
        name.lower() for name in (chat.active_usernames or ()) if name
    )
    if not usernames:
        logger.warning(
            'Telegram returned no active bot usernames; using the primary '
            'username and configured bot_username_aliases',
        )
    for handlers in application.handlers.values():
        for handler in handlers:
            if isinstance(handler, AliasCommandHandler):
                handler.active_usernames = usernames
    logger.info('Loaded %s active bot usernames', len(usernames))


class AliasCommandHandler(CommandHandler):
    """Accept discovered and configured aliases with standard command semantics."""

    active_usernames: frozenset[str] = frozenset()

    def check_update(self, update: object):
        result = super().check_update(update)
        if result is not None:
            return result

        if not isinstance(update, Update) or not filters.COMMAND.check_update(update):
            return None

        message = update.effective_message
        command, separator, username = message.parse_entity(message.entities[0])[1:].partition('@')
        if not separator or command.lower() not in self.commands:
            return None

        if username.lower() not in self.active_usernames:
            configured_aliases = get_config(update.effective_chat.id).constants.bot_username_aliases
            if username.lower() not in {
                name.strip().removeprefix('@').lower() for name in configured_aliases
            }:
                return None

        args = message.text.split()[1:]
        if not self._check_correct_args(args):
            return None

        filter_result = self.filters.check_update(update)
        return (args, filter_result) if filter_result else False
