"""Tests for shop commands."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock
from datetime import date, datetime
from telegram import Update, User, Chat, CallbackQuery
from telegram.ext import CallbackContext

from bot.handlers.game.commands import (
    pidorshop_cmd,
    handle_shop_immunity_callback,
    handle_shop_double_callback,
    handle_shop_double_confirm_callback,
    handle_shop_predict_callback,
    handle_shop_predict_confirm_callback
)
from bot.app.models import TGUser, Game, GamePlayerEffect, Prediction
from bot.handlers.game.coin_service import add_coins


@pytest.fixture
def mock_update():
    """Create a mock Update object."""
    update = MagicMock(spec=Update)
    update.effective_chat = MagicMock(spec=Chat)
    update.effective_chat.id = 12345
    update.effective_chat.send_message = AsyncMock()
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = 100
    update.effective_user.username = "testuser"
    return update


@pytest.fixture
def mock_callback_query(mock_update):
    """Create a mock CallbackQuery object."""
    query = MagicMock(spec=CallbackQuery)
    query.from_user = MagicMock(spec=User)
    query.from_user.id = 100
    query.from_user.username = "testuser"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    mock_update.callback_query = query
    return query


@pytest.fixture
def mock_context(mock_db_session, sample_players):
    """Create a mock CallbackContext with game and tg_user."""
    context = MagicMock(spec=CallbackContext)
    context.db_session = mock_db_session
    context.tg_user = sample_players[0]  # First player (id=100)

    # Create a proper mock for game with players
    game_mock = MagicMock(spec=Game)
    game_mock.id = 1
    # Use a property to ensure players is always returned correctly
    type(game_mock).players = PropertyMock(return_value=sample_players)

    context.game = game_mock
    context.bot = MagicMock()
    return context


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pidorshop_cmd_shows_menu(mock_update, mock_context, mock_db_session):
    """Test that pidorshop_cmd shows menu with buttons."""
    # Mock get_balance to return 100 coins
    mock_db_session.exec.return_value.first.return_value = (100,)

    # Set chat_id for the test
    mock_update.effective_chat.id = -1001392307997

    await pidorshop_cmd(mock_update, mock_context)

    # Verify that send_message was called
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = mock_update.effective_chat.send_message.call_args

    # Check that message contains balance
    assert "100" in call_args[1]["text"]
    # Check that message uses MarkdownV2
    assert call_args[1]["parse_mode"] == "MarkdownV2"
    # Check that reply_markup (keyboard) is present
    assert "reply_markup" in call_args[1]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pidorshop_cmd_shows_balance(mock_update, mock_context, mock_db_session):
    """Test that pidorshop_cmd shows user's balance."""
    # Mock get_balance to return 250 coins
    mock_db_session.exec.return_value.first.return_value = (250,)

    # Set chat_id for the test
    mock_update.effective_chat.id = -1001392307997

    await pidorshop_cmd(mock_update, mock_context)

    # Verify that send_message was called with balance
    call_args = mock_update.effective_chat.send_message.call_args
    assert "250" in call_args[1]["text"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_immunity_callback_success(mock_update, mock_callback_query, mock_context, mock_db_session, sample_players):
    """Test successful immunity purchase."""
    # Setup callback data
    mock_callback_query.data = "shop_immunity_100"
    mock_callback_query.from_user.id = 100

    # Mock get_or_create_player_effects
    effect = GamePlayerEffect(
        id=1,
        game_id=1,
        user_id=100,
        immunity_until=None,
        immunity_last_used=None,
        double_chance_until=None
    )

    with patch('bot.handlers.game.shop_service.get_or_create_player_effects', return_value=effect):
        with patch('bot.handlers.game.coin_service.get_balance', return_value=100):
            with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                await handle_shop_immunity_callback(mock_update, mock_context)

    # Verify success response
    mock_callback_query.answer.assert_called_once()
    assert "✅" in mock_callback_query.answer.call_args[0][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_immunity_callback_insufficient_funds(mock_update, mock_callback_query, mock_context, mock_db_session):
    """Test immunity purchase with insufficient funds."""
    # Setup callback data
    mock_callback_query.data = "shop_immunity_100"
    mock_callback_query.from_user.id = 100

    # Mock get_or_create_player_effects
    effect = GamePlayerEffect(
        id=1,
        game_id=1,
        user_id=100,
        immunity_until=None,
        immunity_last_used=None,
        double_chance_until=None
    )

    with patch('bot.handlers.game.shop_service.get_or_create_player_effects', return_value=effect):
        with patch('bot.handlers.game.coin_service.get_balance', return_value=5):
            with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                await handle_shop_immunity_callback(mock_update, mock_context)

    # Verify error response
    mock_callback_query.answer.assert_called_once()
    assert "❌" in mock_callback_query.answer.call_args[0][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_immunity_callback_already_active(mock_update, mock_callback_query, mock_context, mock_db_session):
    """Test immunity purchase when already active."""
    # Setup callback data
    mock_callback_query.data = "shop_immunity_100"
    mock_callback_query.from_user.id = 100

    # Mock get_or_create_player_effects with active immunity
    effect = GamePlayerEffect(
        id=1,
        game_id=1,
        user_id=100,
        immunity_until=date(2024, 1, 20),  # Active until future date
        immunity_last_used=date(2024, 1, 14),
        double_chance_until=None
    )

    with patch('bot.handlers.game.shop_service.get_or_create_player_effects', return_value=effect):
        with patch('bot.handlers.game.coin_service.get_balance', return_value=100):
            with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                await handle_shop_immunity_callback(mock_update, mock_context)

    # Verify error response
    mock_callback_query.answer.assert_called_once()
    assert "❌" in mock_callback_query.answer.call_args[0][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_immunity_callback_cooldown(mock_update, mock_callback_query, mock_context, mock_db_session):
    """Test immunity purchase when on cooldown."""
    # Setup callback data
    mock_callback_query.data = "shop_immunity_100"
    mock_callback_query.from_user.id = 100

    # Mock get_or_create_player_effects with recent usage (within 7 days)
    effect = GamePlayerEffect(
        id=1,
        game_id=1,
        user_id=100,
        immunity_until=None,  # Not active
        immunity_last_used=date(2024, 1, 10),  # Used 5 days ago
        double_chance_until=None
    )

    with patch('bot.handlers.game.shop_service.get_or_create_player_effects', return_value=effect):
        with patch('bot.handlers.game.coin_service.get_balance', return_value=100):
            with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                await handle_shop_immunity_callback(mock_update, mock_context)

    # Verify error response
    mock_callback_query.answer.assert_called_once()
    assert "❌" in mock_callback_query.answer.call_args[0][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_immunity_callback_not_owner(mock_update, mock_callback_query, mock_context, mock_db_session):
    """Test that non-owner cannot use shop."""
    # Setup callback data with different owner
    mock_callback_query.data = "shop_immunity_200"  # Owner is user 200
    mock_callback_query.from_user.id = 100  # But user 100 is clicking

    await handle_shop_immunity_callback(mock_update, mock_context)

    # Verify error response
    mock_callback_query.answer.assert_called_once()
    call_args = mock_callback_query.answer.call_args
    assert "❌" in call_args[0][0] or "не твой" in call_args[0][0].lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_double_callback_shows_players(mock_update, mock_callback_query, mock_db_session, sample_players):
    """Test that double chance callback shows player list."""
    # Setup callback data
    mock_callback_query.data = "shop_double_100"
    mock_callback_query.from_user.id = 100

    # Create a fresh context with proper game mock
    context = MagicMock(spec=CallbackContext)
    context.db_session = mock_db_session
    context.tg_user = sample_players[0]

    # Create a simple game object with players
    class SimpleGame:
        def __init__(self):
            self.id = 1
            self.players = sample_players

    game = SimpleGame()

    # Mock the database query to return our game (for @ensure_game decorator)
    mock_db_session.query.return_value.filter_by.return_value.one_or_none.return_value = game

    await handle_shop_double_callback(mock_update, context)

    # Verify that edit_message_text was called with player selection
    mock_callback_query.edit_message_text.assert_called_once()
    call_args = mock_callback_query.edit_message_text.call_args

    # Check that reply_markup (keyboard with players) is present
    assert "reply_markup" in call_args[1]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_double_confirm_callback_success(mock_update, mock_callback_query, mock_context, mock_db_session, sample_players):
    """Test successful double chance purchase for self."""
    # Setup callback data
    mock_callback_query.data = "shop_double_confirm_100_100"  # Target user 100, owner 100
    mock_callback_query.from_user.id = 100

    # Ensure context has proper user ID
    mock_context.tg_user.id = 100

    # Mock get_balance to return sufficient funds
    with patch('bot.handlers.game.coin_service.get_balance', return_value=50):
        # Mock shop_service.buy_double_chance to return success with commission
        with patch('bot.handlers.game.shop_service.buy_double_chance', return_value=(True, "success", 1)):
            # Mock query for target user
            mock_db_session.query.return_value.filter_by.return_value.one.return_value = sample_players[0]

            with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                await handle_shop_double_confirm_callback(mock_update, mock_context)

    # Verify success response
    mock_callback_query.answer.assert_called_once()
    assert "✅" in mock_callback_query.answer.call_args[0][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_double_confirm_callback_for_other(mock_update, mock_callback_query, mock_context, mock_db_session, sample_players):
    """Test successful double chance purchase for another player."""
    # Setup callback data
    mock_callback_query.data = "shop_double_confirm_101_100"  # Target user 101, owner 100
    mock_callback_query.from_user.id = 100

    # Ensure context has proper user ID
    mock_context.tg_user.id = 100

    # Mock get_balance to return sufficient funds
    with patch('bot.handlers.game.coin_service.get_balance', return_value=50):
        # Mock shop_service.buy_double_chance to return success with commission
        with patch('bot.handlers.game.shop_service.buy_double_chance', return_value=(True, "success", 1)):
            # Mock query for target user
            mock_db_session.query.return_value.filter_by.return_value.one.return_value = sample_players[1]

            with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                await handle_shop_double_confirm_callback(mock_update, mock_context)

    # Verify success response
    mock_callback_query.answer.assert_called_once()
    assert "✅" in mock_callback_query.answer.call_args[0][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_predict_callback_shows_players(mock_update, mock_callback_query, mock_db_session, sample_players):
    """Test that predict callback shows player list."""
    # Setup callback data
    mock_callback_query.data = "shop_predict_100"
    mock_callback_query.from_user.id = 100

    # Create a fresh context with proper game mock
    context = MagicMock(spec=CallbackContext)
    context.db_session = mock_db_session
    context.tg_user = sample_players[0]

    # Create a simple game object with players
    class SimpleGame:
        def __init__(self):
            self.id = 1
            self.players = sample_players

    game = SimpleGame()

    # Mock the database query to return our game (for @ensure_game decorator)
    mock_db_session.query.return_value.filter_by.return_value.one_or_none.return_value = game

    # Mock get_or_create_prediction_draft to return a draft with empty selection
    with patch('bot.handlers.game.prediction_service.get_or_create_prediction_draft') as mock_get_draft:
        from bot.app.models import PredictionDraft
        mock_draft = PredictionDraft(
            id=1,
            game_id=1,
            user_id=100,
            selected_user_ids='[]',  # Empty JSON array as string
            candidates_count=2
        )
        mock_get_draft.return_value = mock_draft

        await handle_shop_predict_callback(mock_update, context)

    # Verify that edit_message_text was called with player selection
    mock_callback_query.edit_message_text.assert_called_once()
    call_args = mock_callback_query.edit_message_text.call_args

    # Check that reply_markup (keyboard with players) is present
    assert "reply_markup" in call_args[1]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_predict_confirm_callback_success(mock_update, mock_callback_query, mock_context, mock_db_session, sample_players):
    """Test successful prediction creation."""
    # Setup callback data
    mock_callback_query.data = "shop_predict_confirm_100"  # owner 100
    mock_callback_query.from_user.id = 100

    # Ensure context has proper user ID
    mock_context.tg_user.id = 100

    # Mock get_balance to return sufficient funds (return int, not tuple)
    with patch('bot.handlers.game.coin_service.get_balance', return_value=150):
        # Mock get_prediction_draft to return a draft with selected candidates
        with patch('bot.handlers.game.prediction_service.get_prediction_draft') as mock_get_draft:
            from bot.app.models import PredictionDraft
            mock_draft = PredictionDraft(
                id=1,
                game_id=1,
                user_id=100,
                selected_user_ids='[101, 102]',  # JSON array as string
                candidates_count=2
            )
            mock_get_draft.return_value = mock_draft

            # Mock shop_service.create_prediction to return success with commission
            with patch('bot.handlers.game.shop_service.create_prediction', return_value=(True, "success", 1)):
                # Mock delete_prediction_draft
                with patch('bot.handlers.game.prediction_service.delete_prediction_draft'):
                    with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                        mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                        await handle_shop_predict_confirm_callback(mock_update, mock_context)

    # Verify success response
    mock_callback_query.answer.assert_called_once()
    assert "✅" in mock_callback_query.answer.call_args[0][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_predict_confirm_callback_already_exists(mock_update, mock_callback_query, mock_context, mock_db_session, sample_players):
    """Test prediction creation when already exists."""
    # Setup callback data
    mock_callback_query.data = "shop_predict_confirm_100"
    mock_callback_query.from_user.id = 100

    # Mock get_balance to return sufficient funds (return int, not tuple)
    with patch('bot.handlers.game.coin_service.get_balance', return_value=150):
        # Mock get_prediction_draft to return a draft with selected candidates
        with patch('bot.handlers.game.prediction_service.get_prediction_draft') as mock_get_draft:
            from bot.app.models import PredictionDraft
            mock_draft = PredictionDraft(
                id=1,
                game_id=1,
                user_id=100,
                selected_user_ids='[101]',  # JSON array as string
                candidates_count=1
            )
            mock_get_draft.return_value = mock_draft

            # Mock shop_service.create_prediction to return error with 0 commission
            with patch('bot.handlers.game.shop_service.create_prediction', return_value=(False, "already_exists", 0)):
                with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                    mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                    await handle_shop_predict_confirm_callback(mock_update, mock_context)

    # Verify error response
    mock_callback_query.answer.assert_called_once()
    assert "❌" in mock_callback_query.answer.call_args[0][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_predict_confirm_callback_self(mock_update, mock_callback_query, mock_context, mock_db_session):
    """Test that user CAN predict themselves (restriction removed)."""
    # Setup callback data - user predicting themselves
    mock_callback_query.data = "shop_predict_confirm_100"
    mock_callback_query.from_user.id = 100

    # Mock get_balance to return sufficient funds (return int, not tuple)
    with patch('bot.handlers.game.coin_service.get_balance', return_value=150):
        # Mock get_prediction_draft to return a draft with self-selection
        with patch('bot.handlers.game.prediction_service.get_prediction_draft') as mock_get_draft:
            from bot.app.models import PredictionDraft
            mock_draft = PredictionDraft(
                id=1,
                game_id=1,
                user_id=100,
                selected_user_ids='[100]',  # Self-prediction as JSON array
                candidates_count=1
            )
            mock_get_draft.return_value = mock_draft

            # Mock shop_service.create_prediction to return success with commission (self-prediction now allowed)
            with patch('bot.handlers.game.shop_service.create_prediction', return_value=(True, "success", 1)):
                # Mock delete_prediction_draft
                with patch('bot.handlers.game.prediction_service.delete_prediction_draft'):
                    with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                        mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                        await handle_shop_predict_confirm_callback(mock_update, mock_context)

    # Verify success response (self-prediction is now allowed)
    mock_callback_query.answer.assert_called_once()
    assert "✅" in mock_callback_query.answer.call_args[0][0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_handle_shop_predict_confirm_callback_insufficient_funds(mock_update, mock_callback_query, mock_context, mock_db_session):
    """Test prediction creation with insufficient funds."""
    # Setup callback data
    mock_callback_query.data = "shop_predict_confirm_100"
    mock_callback_query.from_user.id = 100

    # Mock get_balance to return insufficient funds (10 coins, return int not tuple)
    with patch('bot.handlers.game.coin_service.get_balance', return_value=10):
        # Mock get_prediction_draft to return a draft with selected candidates
        with patch('bot.handlers.game.prediction_service.get_prediction_draft') as mock_get_draft:
            from bot.app.models import PredictionDraft
            mock_draft = PredictionDraft(
                id=1,
                game_id=1,
                user_id=100,
                selected_user_ids='[101]',  # JSON array as string
                candidates_count=1
            )
            mock_get_draft.return_value = mock_draft

            # Mock shop_service.create_prediction to return error with 0 commission
            with patch('bot.handlers.game.shop_service.create_prediction', return_value=(False, "insufficient_funds", 0)):
                with patch('bot.handlers.game.commands.current_datetime') as mock_dt:
                    mock_dt.return_value = datetime(2024, 1, 15, 12, 0, 0)

                    await handle_shop_predict_confirm_callback(mock_update, mock_context)

    # Verify error response
    mock_callback_query.answer.assert_called_once()
    assert "❌" in mock_callback_query.answer.call_args[0][0]
