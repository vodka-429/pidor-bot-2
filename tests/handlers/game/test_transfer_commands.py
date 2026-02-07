import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update, Chat, Message, User, CallbackQuery, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bot.app.models import Game, TGUser, ChatBank, CoinTransfer
from bot.handlers.game.commands import (
    handle_shop_transfer_callback,
    handle_shop_transfer_select_callback,
    handle_shop_bank_callback,
    handle_shop_back_callback,
    GECallbackContext
)


MOSCOW_TZ = ZoneInfo('Europe/Moscow')


@pytest.fixture
def mock_update():
    """Создаёт мок Update с callback_query"""
    update = MagicMock(spec=Update)
    update.callback_query = MagicMock(spec=CallbackQuery)
    update.callback_query.from_user = MagicMock(spec=User)
    update.callback_query.from_user.id = 123456
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()
    update.effective_chat = MagicMock(spec=Chat)
    update.effective_chat.id = -100123456789
    update.effective_chat.send_message = AsyncMock()
    return update


@pytest.fixture
def sample_players():
    """Создаёт список игроков для тестов"""
    players = []
    # Отправитель
    sender = TGUser(
        id=1,
        tg_id=123456,
        username="sender",
        first_name="Sender"
    )
    # Получатель
    receiver = TGUser(
        id=2,
        tg_id=654321,
        username="receiver",
        first_name="Receiver"
    )
    # Другой игрок
    other = TGUser(
        id=3,
        tg_id=111111,
        username="other",
        first_name="Other"
    )

    players.extend([sender, receiver, other])
    return players


@pytest.fixture
def mock_context(mock_db_session, sample_players):
    """Создаёт мок контекста с игрой и пользователем"""
    context = MagicMock(spec=GECallbackContext)
    context.db_session = mock_db_session

    # Создаём мок игры с правильными атрибутами
    game = MagicMock()
    game.id = 1
    game.chat_id = -100123456789
    game.players = sample_players
    # Добавляем атрибут __bool__ чтобы game оценивался как True
    game.__bool__ = MagicMock(return_value=True)
    game.__len__ = MagicMock(return_value=len(sample_players))

    context.game = game
    context.tg_user = sample_players[0]  # sender
    context.bot = MagicMock()

    # Настраиваем mock_db_session чтобы @ensure_game декоратор возвращал наш game
    # query(Game).filter_by(chat_id=...).one_or_none() должен вернуть game
    mock_db_session.query.return_value.filter_by.return_value.one_or_none.return_value = game

    return context


class TestShopTransferCallback:
    """Тесты для handle_shop_transfer_callback"""

    @pytest.mark.asyncio
    async def test_successful_show_player_list(self, mock_update, mock_context):
        """Тест успешного показа списка игроков для передачи"""
        # Настраиваем callback_data
        mock_update.callback_query.data = "shop_transfer_123456"

        # Вызываем обработчик
        await handle_shop_transfer_callback(mock_update, mock_context)

        # Проверяем, что был вызван edit_message_text с правильными параметрами
        mock_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_update.callback_query.edit_message_text.call_args

        # Проверяем текст сообщения
        assert "Выберите получателя" in call_args[1]['text']
        assert call_args[1]['parse_mode'] == "MarkdownV2"

        # Проверяем, что есть клавиатура с игроками
        keyboard = call_args[1]['reply_markup']
        assert isinstance(keyboard, InlineKeyboardMarkup)

        # Проверяем, что answer был вызван
        mock_update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_wrong_user_access(self, mock_update, mock_context):
        """Тест попытки доступа к чужому магазину"""
        # Настраиваем callback_data с другим owner_user_id
        mock_update.callback_query.data = "shop_transfer_999999"

        # Вызываем обработчик
        await handle_shop_transfer_callback(mock_update, mock_context)

        # Проверяем, что был показан alert
        mock_update.callback_query.answer.assert_called_once()
        call_args = mock_update.callback_query.answer.call_args
        assert "Это не твой магазин" in call_args[0][0]
        assert call_args[1]['show_alert'] is True

        # Проверяем, что сообщение не было изменено
        mock_update.callback_query.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_other_players(self, mock_update, mock_context):
        """Тест когда нет других игроков для передачи"""
        # Оставляем только одного игрока
        mock_context.game.players = [mock_context.tg_user]

        # Настраиваем callback_data
        mock_update.callback_query.data = "shop_transfer_123456"

        # Вызываем обработчик
        await handle_shop_transfer_callback(mock_update, mock_context)

        # Проверяем, что был показан alert об ошибке
        mock_update.callback_query.answer.assert_called_once()
        call_args = mock_update.callback_query.answer.call_args
        assert "Нет других игроков" in call_args[0][0]
        assert call_args[1]['show_alert'] is True


class TestShopTransferSelectCallback:
    """Тесты для handle_shop_transfer_select_callback - показ клавиатуры с выбором суммы"""

    @pytest.mark.asyncio
    @patch('bot.handlers.game.commands.get_balance')
    async def test_show_amount_selection(self, mock_get_balance, mock_update, mock_context, mock_db_session):
        """Тест показа клавиатуры с выбором суммы"""
        # Настраиваем баланс
        mock_get_balance.return_value = 100

        # Настраиваем получателя
        receiver = mock_context.game.players[1]
        mock_db_session.query.return_value.filter_by.return_value.one.return_value = receiver

        # Set chat_id for the test
        mock_update.effective_chat.id = -100123456789

        # Настраиваем callback_data (receiver_id=2, owner_id=123456)
        mock_update.callback_query.data = "shop_transfer_select_2_123456"

        # Вызываем обработчик
        await handle_shop_transfer_select_callback(mock_update, mock_context)

        # Проверяем ответ
        mock_update.callback_query.answer.assert_called_once()

        # Проверяем сообщение с клавиатурой
        mock_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert "Выберите сумму перевода" in call_args[1]['text']
        assert "receiver" in call_args[1]['text']  # Имя получателя (username)
        assert "100" in call_args[1]['text']  # Баланс
        assert call_args[1]['parse_mode'] == "MarkdownV2"

        # Проверяем, что есть клавиатура
        keyboard = call_args[1]['reply_markup']
        assert isinstance(keyboard, InlineKeyboardMarkup)

    @pytest.mark.asyncio
    @patch('bot.handlers.game.commands.get_balance')
    async def test_insufficient_balance(self, mock_get_balance, mock_update, mock_context):
        """Тест недостаточного баланса (меньше минимума)"""
        # Настраиваем маленький баланс
        mock_get_balance.return_value = 1  # Меньше минимума (2)

        # Настраиваем callback_data
        mock_update.callback_query.data = "shop_transfer_select_2_123456"

        # Вызываем обработчик
        await handle_shop_transfer_select_callback(mock_update, mock_context)

        # Проверяем, что был показан alert об ошибке
        mock_update.callback_query.answer.assert_called_once()
        call_args = mock_update.callback_query.answer.call_args
        assert "Недостаточно койнов" in call_args[0][0]
        assert call_args[1]['show_alert'] is True

    @pytest.mark.asyncio
    async def test_wrong_user_access(self, mock_update, mock_context):
        """Тест попытки доступа к чужому переводу"""
        # Настраиваем callback_data с другим owner_user_id
        mock_update.callback_query.data = "shop_transfer_select_2_999999"

        # Вызываем обработчик
        await handle_shop_transfer_select_callback(mock_update, mock_context)

        # Проверяем, что был показан alert
        mock_update.callback_query.answer.assert_called_once()
        call_args = mock_update.callback_query.answer.call_args
        assert "Это не твой магазин" in call_args[0][0]
        assert call_args[1]['show_alert'] is True


class TestShopTransferAmountCallback:
    """Тесты для handle_shop_transfer_amount_callback - выполнение перевода"""

    @pytest.mark.asyncio
    @patch('bot.handlers.game.commands.current_datetime')
    @patch('bot.handlers.game.commands.get_balance')
    @patch('bot.handlers.game.transfer_service.execute_transfer')
    @patch('bot.handlers.game.transfer_service.can_transfer')
    @patch('bot.handlers.game.transfer_service.get_or_create_chat_bank')
    async def test_successful_transfer(self, mock_get_bank, mock_can_transfer, mock_execute_transfer,
                                     mock_get_balance, mock_current_datetime,
                                     mock_update, mock_context, mock_db_session):
        """Тест успешной передачи койнов"""
        # Настраиваем мок времени
        mock_current_datetime.return_value = datetime(2024, 1, 15, 12, 0, tzinfo=MOSCOW_TZ)

        # Настраиваем моки
        mock_can_transfer.return_value = (True, "ok")
        mock_get_balance.side_effect = [100, 50, 95]  # sender до, sender после, receiver после
        mock_execute_transfer.return_value = (50, 45, 5)  # sent, received, commission

        # Настраиваем банк
        bank = MagicMock()
        bank.balance = 5
        mock_get_bank.return_value = bank

        # Настраиваем получателя
        receiver = mock_context.game.players[1]
        mock_db_session.query.return_value.filter_by.return_value.one.return_value = receiver

        # Настраиваем callback_data (receiver_id=2, amount=50, owner_id=123456)
        mock_update.callback_query.data = "shop_transfer_amount_2_50_123456"

        # Вызываем обработчик
        from bot.handlers.game.commands import handle_shop_transfer_amount_callback
        await handle_shop_transfer_amount_callback(mock_update, mock_context)

        # Проверяем вызовы
        mock_can_transfer.assert_called_once_with(mock_db_session, 1, 1, 2024, 15)
        mock_execute_transfer.assert_called_once_with(
            mock_db_session, 1, 1, 2, 50, 2024, 15
        )

        # Проверяем ответ
        mock_update.callback_query.answer.assert_called_once_with(
            "✅ Перевод выполнен!", show_alert=True
        )

        # Проверяем сообщение
        mock_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert "Перевод выполнен" in call_args[1]['text']
        assert "50" in call_args[1]['text']  # Сумма
        assert "45" in call_args[1]['text']  # Получено (50-5)
        assert "5" in call_args[1]['text']   # Комиссия

    @pytest.mark.asyncio
    @patch('bot.handlers.game.commands.current_datetime')
    @patch('bot.handlers.game.transfer_service.can_transfer')
    async def test_transfer_cooldown(self, mock_can_transfer, mock_current_datetime,
                                   mock_update, mock_context):
        """Тест кулдауна передачи (уже передавал сегодня)"""
        # Настраиваем мок времени
        mock_current_datetime.return_value = datetime(2024, 1, 15, 12, 0, tzinfo=MOSCOW_TZ)

        # Настраиваем отказ из-за кулдауна
        mock_can_transfer.return_value = (False, "already_transferred_today")

        # Настраиваем callback_data
        mock_update.callback_query.data = "shop_transfer_amount_2_50_123456"

        # Вызываем обработчик
        from bot.handlers.game.commands import handle_shop_transfer_amount_callback
        await handle_shop_transfer_amount_callback(mock_update, mock_context)

        # Проверяем, что был показан alert об ошибке
        mock_update.callback_query.answer.assert_called_once()
        call_args = mock_update.callback_query.answer.call_args
        assert "уже совершали перевод сегодня" in call_args[0][0]
        assert call_args[1]['show_alert'] is True

        # Проверяем сообщение об ошибке
        mock_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert "уже совершали перевод сегодня" in call_args[1]['text']

    @pytest.mark.asyncio
    @patch('bot.handlers.game.commands.current_datetime')
    @patch('bot.handlers.game.commands.get_balance')
    @patch('bot.handlers.game.transfer_service.can_transfer')
    async def test_insufficient_funds(self, mock_can_transfer, mock_get_balance, mock_current_datetime,
                                    mock_update, mock_context):
        """Тест недостаточного баланса для передачи"""
        # Настраиваем мок времени
        mock_current_datetime.return_value = datetime(2024, 1, 15, 12, 0, tzinfo=MOSCOW_TZ)

        # Настраиваем разрешение на передачу
        mock_can_transfer.return_value = (True, "ok")

        # Настраиваем маленький баланс
        mock_get_balance.return_value = 30  # Меньше запрошенной суммы (50)

        # Настраиваем callback_data (amount=50)
        mock_update.callback_query.data = "shop_transfer_amount_2_50_123456"

        # Вызываем обработчик
        from bot.handlers.game.commands import handle_shop_transfer_amount_callback
        await handle_shop_transfer_amount_callback(mock_update, mock_context)

        # Проверяем, что был показан alert об ошибке
        mock_update.callback_query.answer.assert_called_once()
        call_args = mock_update.callback_query.answer.call_args
        assert "Недостаточно койнов" in call_args[0][0]
        assert "30" in call_args[0][0]  # Текущий баланс
        assert call_args[1]['show_alert'] is True

    @pytest.mark.asyncio
    async def test_wrong_user_access(self, mock_update, mock_context):
        """Тест попытки доступа к чужому переводу"""
        # Настраиваем callback_data с другим owner_user_id
        mock_update.callback_query.data = "shop_transfer_amount_2_50_999999"

        # Вызываем обработчик
        from bot.handlers.game.commands import handle_shop_transfer_amount_callback
        await handle_shop_transfer_amount_callback(mock_update, mock_context)

        # Проверяем, что был показан alert
        mock_update.callback_query.answer.assert_called_once()
        call_args = mock_update.callback_query.answer.call_args
        assert "Это не твой магазин" in call_args[0][0]
        assert call_args[1]['show_alert'] is True


class TestShopBankCallback:
    """Тесты для handle_shop_bank_callback"""

    @pytest.mark.asyncio
    @patch('bot.handlers.game.transfer_service.get_or_create_chat_bank')
    async def test_show_bank_balance(self, mock_get_bank, mock_update, mock_context):
        """Тест показа баланса банка"""
        # Настраиваем банк
        bank = MagicMock()
        bank.balance = 150
        mock_get_bank.return_value = bank

        # Настраиваем callback_data
        mock_update.callback_query.data = "shop_bank_123456"

        # Вызываем обработчик
        await handle_shop_bank_callback(mock_update, mock_context)

        # Проверяем ответ
        mock_update.callback_query.answer.assert_called_once()

        # Проверяем сообщение
        mock_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert "Банк чата" in call_args[1]['text']
        assert "150" in call_args[1]['text']
        assert call_args[1]['parse_mode'] == "MarkdownV2"

    @pytest.mark.asyncio
    @patch('bot.handlers.game.transfer_service.get_or_create_chat_bank')
    async def test_show_empty_bank(self, mock_get_bank, mock_update, mock_context):
        """Тест показа пустого банка"""
        # Настраиваем пустой банк
        bank = MagicMock()
        bank.balance = 0
        mock_get_bank.return_value = bank

        # Настраиваем callback_data
        mock_update.callback_query.data = "shop_bank_123456"

        # Вызываем обработчик
        await handle_shop_bank_callback(mock_update, mock_context)

        # Проверяем сообщение
        mock_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert "Банк чата" in call_args[1]['text']
        assert "0" in call_args[1]['text']

    @pytest.mark.asyncio
    async def test_wrong_user_access(self, mock_update, mock_context):
        """Тест попытки доступа к чужому банку"""
        # Настраиваем callback_data с другим owner_user_id
        mock_update.callback_query.data = "shop_bank_999999"

        # Вызываем обработчик
        await handle_shop_bank_callback(mock_update, mock_context)

        # Проверяем, что был показан alert
        mock_update.callback_query.answer.assert_called_once()
        call_args = mock_update.callback_query.answer.call_args
        assert "Это не твой магазин" in call_args[0][0]
        assert call_args[1]['show_alert'] is True


class TestShopBackCallback:
    """Тесты для handle_shop_back_callback"""

    @pytest.mark.asyncio
    @patch('bot.handlers.game.commands.get_balance')
    @patch('bot.handlers.game.commands.current_datetime')
    @patch('bot.handlers.game.shop_service.get_active_effects')
    async def test_return_to_shop_menu(self, mock_get_active_effects, mock_current_datetime,
                                      mock_get_balance, mock_update, mock_context):
        """Тест возврата в главное меню магазина"""
        # Настраиваем моки
        mock_current_datetime.return_value = datetime(2024, 1, 15, 12, 0, tzinfo=MOSCOW_TZ)
        mock_get_balance.return_value = 75
        mock_get_active_effects.return_value = {
            'immunity': None,
            'double_chance': None,
            'prediction': None
        }

        # Set chat_id for the test
        mock_update.effective_chat.id = -100123456789

        # Настраиваем callback_data
        mock_update.callback_query.data = "shop_back_123456"

        # Вызываем обработчик
        await handle_shop_back_callback(mock_update, mock_context)

        # Проверяем ответ
        mock_update.callback_query.answer.assert_called_once()

        # Проверяем сообщение
        mock_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_update.callback_query.edit_message_text.call_args
        assert "Магазин пидор\\-койнов" in call_args[1]['text']
        assert "75" in call_args[1]['text']  # Баланс
        assert call_args[1]['parse_mode'] == "MarkdownV2"

        # Проверяем, что есть клавиатура
        keyboard = call_args[1]['reply_markup']
        assert isinstance(keyboard, InlineKeyboardMarkup)

    @pytest.mark.asyncio
    async def test_wrong_user_access(self, mock_update, mock_context):
        """Тест попытки доступа к чужой кнопке назад"""
        # Настраиваем callback_data с другим owner_user_id
        mock_update.callback_query.data = "shop_back_999999"

        # Вызываем обработчик
        await handle_shop_back_callback(mock_update, mock_context)

        # Проверяем, что был показан alert
        mock_update.callback_query.answer.assert_called_once()
        call_args = mock_update.callback_query.answer.call_args
        assert "Это не твой магазин" in call_args[0][0]
        assert call_args[1]['show_alert'] is True
