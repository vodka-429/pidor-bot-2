import asyncio
from unittest.mock import AsyncMock

import pytest
from telegram import AcceptedGiftTypes, Chat, ChatFullInfo, Message, MessageEntity, Update, User
from telegram.error import BadRequest, NetworkError
from telegram.ext import (
    Application, CallbackContext, CommandHandler, ContextTypes, ExtBot,
    SimpleUpdateProcessor, filters,
)

from bot.command_handler import AliasCommandHandler, load_bot_username_aliases
from bot.dispatcher import init_dispatcher
from bot.handlers.game.commands import current_datetime
from bot.handlers.game.config import ChatConfig, GameConstants


def bot_chat_info(*, bot_id=123, active_usernames=()):
    return ChatFullInfo(
        id=bot_id, type=Chat.PRIVATE, accent_color_id=0, max_reaction_count=0,
        accepted_gift_types=AcceptedGiftTypes(False, False, False, False, False),
        active_usernames=active_usernames,
    )


@pytest.fixture
async def application(mocker):
    mocker.patch('bot.dispatcher.get_enabled_chats', return_value=[-123])
    mocker.patch('bot.command_handler.get_config', return_value=ChatConfig(chat_id=-123))
    # Command routing tests do not need a scheduler, updater, or persistence.
    app = Application(
        bot=ExtBot('123:test'),
        update_queue=asyncio.Queue(),
        updater=None,
        job_queue=None,
        update_processor=SimpleUpdateProcessor(1),
        persistence=None,
        context_types=ContextTypes(),
        post_init=None,
        post_shutdown=None,
        post_stop=None,
    )
    app.bot._bot_user = User(
        id=123, first_name='PidorVodkaBot', is_bot=True, username='PidorVodkaBot',
    )
    init_dispatcher(app, None)
    mocker.patch.object(type(app.bot), 'get_chat', new_callable=AsyncMock, return_value=bot_chat_info(
        active_usernames=['PidorVodkaBot', 'PidorVodkaGay'],
    ))
    await load_bot_username_aliases(app)
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
    handler.active_usernames = frozenset({'pidorvodkagay'})
    update = command_update(application, f'/test@PidorVodkaGay{arguments}')

    assert bool(handler.check_update(update)) is accepted


@pytest.mark.asyncio
async def test_alias_preserves_data_filters(application):
    handler = AliasCommandHandler('test', AsyncMock(), filters=filters.Regex(r'value=(\d+)'))
    handler.active_usernames = frozenset({'pidorvodkagay'})
    update = command_update(application, '/test@PidorVodkaGay value=42')
    context = CallbackContext(application)
    result = handler.check_update(update)

    assert result
    await handler.handle_update(update, application, result, context)

    assert context.args == ['value=42']
    assert context.matches[0].group(1) == '42'


@pytest.mark.asyncio
async def test_discovery_accepts_new_aliases_and_replaces_old_ones(application):
    application.bot.get_chat.reset_mock()
    application.bot.get_chat.return_value = bot_chat_info(
        active_usernames=['PidorVodkaBot', 'AnotherAliasGame'],
    )

    await load_bot_username_aliases(application)

    application.bot.get_chat.assert_awaited_once_with(123)
    handler = handler_for(application, 'pidorshop')
    assert handler.check_update(command_update(application, '/pidorshop@AnotherAliasGame'))
    assert not handler.check_update(command_update(application, '/pidorshop@PidorVodkaGay'))


@pytest.mark.asyncio
async def test_discovery_retries_by_current_username(application):
    application.bot.get_chat.reset_mock()
    application.bot.get_chat.side_effect = [
        BadRequest('Chat not found'),
        bot_chat_info(
            active_usernames=['PidorVodkaBot', 'AnotherAliasAi'],
        ),
    ]

    await load_bot_username_aliases(application)

    assert [call.args[0] for call in application.bot.get_chat.await_args_list] == [
        123, '@PidorVodkaBot',
    ]
    assert handler_for(application, 'pidorshop').check_update(
        command_update(application, '/pidorshop@AnotherAliasAi'),
    )


@pytest.mark.asyncio
async def test_discovery_rejects_different_bot_id(application, caplog):
    application.bot.get_chat.return_value = bot_chat_info(
        bot_id=999,
        active_usernames=['OtherBot'],
    )

    await load_bot_username_aliases(application)

    assert not handler_for(application, 'pidorshop').check_update(
        command_update(application, '/pidorshop@OtherBot'),
    )
    assert 'different bot ID' in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [NetworkError('API unavailable'), BadRequest('Chat not found')])
async def test_discovery_failure_keeps_primary_and_configured_aliases(application, mocker, caplog, error):
    application.bot.get_chat.side_effect = error
    handler = handler_for(application, 'pidorshop')
    handler.active_usernames = frozenset()
    mocker.patch('bot.command_handler.get_config', return_value=ChatConfig(
        chat_id=-123, constants=GameConstants(bot_username_aliases=[' @ManualAliasAi ']),
    ))

    await load_bot_username_aliases(application)

    for suffix in ('', '@PidorVodkaBot', '@ManualAliasAi'):
        assert handler.check_update(command_update(application, f'/pidorshop{suffix}'))
    assert not handler.check_update(command_update(application, '/pidorshop@PidorVodkaGay'))
    assert 'configured bot_username_aliases' in caplog.text


@pytest.mark.asyncio
async def test_discovery_handles_missing_active_usernames(application, caplog):
    application.bot.get_chat.return_value = bot_chat_info()

    await load_bot_username_aliases(application)

    handler = handler_for(application, 'pidorshop')
    assert handler.check_update(command_update(application, '/pidorshop@PidorVodkaBot'))
    assert not handler.check_update(command_update(application, '/pidorshop@PidorVodkaGay'))
    assert 'no active bot usernames' in caplog.text
