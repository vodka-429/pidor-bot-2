"""Command routing for the bot's regular and collectible usernames."""

from telegram import Update
from telegram.ext import CommandHandler, filters


# getMe exposes only one username, even when BotFather lists multiple active names.
BOT_USERNAME_ALIASES = frozenset({'pidorvodkabot', 'pidorvodkagay'})


class AliasCommandHandler(CommandHandler):
    """Keep standard command handling and also accept the bot's known aliases."""

    def check_update(self, update: object):
        result = super().check_update(update)
        if result is not None:
            return result

        if not isinstance(update, Update) or not filters.COMMAND.check_update(update):
            return None

        message = update.effective_message
        command, separator, username = message.parse_entity(message.entities[0])[1:].partition('@')
        if (
            not separator
            or username.lower() not in BOT_USERNAME_ALIASES
            or command.lower() not in self.commands
        ):
            return None

        args = message.text.split()[1:]
        if not self._check_correct_args(args):
            return None

        filter_result = self.filters.check_update(update)
        return (args, filter_result) if filter_result else False
