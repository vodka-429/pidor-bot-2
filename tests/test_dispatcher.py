from unittest.mock import AsyncMock

import pytest
from telegram import Chat, Message, MessageEntity, Update, User
from telegram.ext import Application, CallbackContext, CommandHandler, filters

from bot.command_handler import AliasCommandHandler
from bot.dispatcher import init_dispatcher
from bot.handlers.game.commands import current_datetime


@pytest.fixture
def application(mocker):
    mocker.patch('bot.dispatcher.get_enabled_chats', return_value=[-123])
    app = Application.builder().token('123:test').build()
    app.bot._bot_user = User(
        id=123, first_name='PidorVodkaBot', is_bot=True, username='PidorVodkaBot',
    )
    init_dispatcher(app, None)
    return app


def command_update(application, text, *, chat_id=-123, edited=False, entities=True):
    message = Message(
        message_id=1,
        date=current_datetime(),
        chat=Chat(id=chat_id, type=Chat.SUPERGROUP),
        from_user=User(id=456, first_name='Player', is_bot=False),
        text=text,
        entities=[MessageEntity(MessageEntity.BOT_COMMAND, 0, len(text.split()[0]))]
        if entities else [],
    )
    message.set_bot(application.bot)
    return Update(1, edited_message=message) if edited else Update(1, message=message)


def handler_for(application, command):
    return next(
        handler for handler in application.handlers[0]
        if isinstance(handler, CommandHandler) and command in handler.commands
    )


@pytest.mark.parametrize('suffix', [
    '', '@PidorVodkaBot', '@PidorVodkaGay', '@pidorvodkagay', '@PIDORVODKABOT',
])
@pytest.mark.parametrize('command', ['pidorstats', 'pidorcoinsstats', 'pidorshop'])
@pytest.mark.parametrize('primary_username', ['PidorVodkaBot', 'PidorVodkaGay'])
def test_commands_accept_both_bot_usernames(application, command, suffix, primary_username):
    application.bot._bot_user = User(
        id=123, first_name='PidorVodkaBot', is_bot=True, username=primary_username,
    )
    update = command_update(application, f'/{command}{suffix}')

    assert handler_for(application, command).check_update(update)


@pytest.mark.parametrize('suffix', [
    '@OtherBot', '@PidorVodkaGayExtra', '@PidorVodka', '@PidorVodkaGay@OtherBot',
])
def test_commands_ignore_other_bot_usernames(application, suffix):
    update = command_update(application, f'/pidorshop{suffix}')

    assert not handler_for(application, 'pidorshop').check_update(update)


@pytest.mark.parametrize('suffix', ['', '@PidorVodkaBot', '@PidorVodkaGay'])
@pytest.mark.parametrize('options', [
    {'chat_id': -999}, {'edited': True}, {'entities': False},
])
def test_commands_preserve_filters_and_entity_checks(application, suffix, options):
    update = command_update(application, f'/pidorshop{suffix}', **options)

    assert not handler_for(application, 'pidorshop').check_update(update)


@pytest.mark.asyncio
async def test_alias_preserves_arguments_and_original_message(application):
    update = command_update(application, '/pidorbirthday@PidorVodkaGay 15.06')
    handler = handler_for(application, 'pidorbirthday')
    callback = AsyncMock()
    handler.callback = callback
    context = CallbackContext(application)
    result = handler.check_update(update)

    assert result
    await handler.handle_update(update, application, result, context)

    assert context.args == ['15.06']
    assert update.message.text == '/pidorbirthday@PidorVodkaGay 15.06'
    assert update.message.get_bot() is application.bot
    assert application.bot.username == 'PidorVodkaBot'
    callback.assert_awaited_once_with(update, context)


def test_commands_keep_runtime_bot_username(application):
    application.bot._bot_user = User(
        id=123, first_name='Test bot', is_bot=True, username='TestDeploymentBot',
    )
    update = command_update(application, '/pidorshop@TestDeploymentBot')

    assert handler_for(application, 'pidorshop').check_update(update)


def test_alias_accepts_mixed_case_command(application):
    update = command_update(application, '/PiDoRCoInSStats@PIDORVODKAGAY')

    assert handler_for(application, 'pidorcoinsstats').check_update(update)


@pytest.mark.parametrize('has_args,arguments,accepted', [
    (True, '', False), (True, ' one', True),
    (False, '', True), (False, ' one', False),
    (2, ' one', False), (2, ' one  two', True),
])
def test_alias_preserves_argument_constraints(application, has_args, arguments, accepted):
    handler = AliasCommandHandler('test', AsyncMock(), has_args=has_args)
    update = command_update(application, f'/test@PidorVodkaGay{arguments}')

    assert bool(handler.check_update(update)) is accepted


@pytest.mark.asyncio
async def test_alias_preserves_data_filters(application):
    handler = AliasCommandHandler('test', AsyncMock(), filters=filters.Regex(r'value=(\d+)'))
    update = command_update(application, '/test@PidorVodkaGay value=42')
    context = CallbackContext(application)
    result = handler.check_update(update)

    assert result
    await handler.handle_update(update, application, result, context)

    assert context.args == ['value=42']
    assert context.matches[0].group(1) == '42'
