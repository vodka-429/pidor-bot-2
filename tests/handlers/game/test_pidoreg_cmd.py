"""Tests for pidoreg_cmd command."""
import pytest
from unittest.mock import MagicMock
from bot.handlers.game.commands import pidoreg_cmd
from bot.handlers.game.text_static import (
    ERROR_ZERO_PLAYERS,
    REGISTRATION_SUCCESS,
    ERROR_ALREADY_REGISTERED,
)


@pytest.mark.unit
def test_pidoreg_cmd_first_player(mock_update, mock_context, mock_game):
    """Test registration of the first player."""
    # Setup: game with no players
    mock_game.players = []
    mock_context.game = mock_game
    
    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Execute
    pidoreg_cmd(mock_update, mock_context)
    
    # Verify ERROR_ZERO_PLAYERS was sent
    mock_update.effective_chat.send_message.assert_called_once()
    call_args = str(mock_update.effective_chat.send_message.call_args)
    assert "TestUser" in call_args or ERROR_ZERO_PLAYERS[:20] in call_args
    
    # Verify REGISTRATION_SUCCESS was sent
    mock_update.effective_message.reply_markdown_v2.assert_called_once_with(REGISTRATION_SUCCESS)
    
    # Verify player was added
    assert mock_context.tg_user in mock_game.players


@pytest.mark.unit
def test_pidoreg_cmd_successful_registration(mock_update, mock_context, mock_game, sample_players):
    """Test successful registration of a new player."""
    # Setup: game with existing players
    mock_game.players = sample_players.copy()
    mock_context.game = mock_game
    
    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Execute
    pidoreg_cmd(mock_update, mock_context)
    
    # Verify REGISTRATION_SUCCESS was sent
    mock_update.effective_message.reply_markdown_v2.assert_called_once_with(REGISTRATION_SUCCESS)
    
    # Verify player was added to the game
    assert mock_context.tg_user in mock_game.players


@pytest.mark.unit
def test_pidoreg_cmd_already_registered(mock_update, mock_context, mock_game, mock_tg_user):
    """Test that error is sent when player is already registered."""
    # Setup: game with player already registered
    mock_game.players = [mock_tg_user]
    mock_context.game = mock_game
    mock_context.tg_user = mock_tg_user
    
    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Execute
    pidoreg_cmd(mock_update, mock_context)
    
    # Verify ERROR_ALREADY_REGISTERED was sent
    mock_update.effective_message.reply_markdown_v2.assert_called_once_with(ERROR_ALREADY_REGISTERED)
    
    # Verify player list length didn't change
    assert len(mock_game.players) == 1


@pytest.mark.unit
def test_pidoreg_cmd_adds_player_to_game(mock_update, mock_context, mock_game):
    """Test that player is added to game.players and committed."""
    # Setup: game with no players
    mock_game.players = []
    mock_context.game = mock_game
    
    # Mock the query chain for ensure_game decorator
    mock_game_query = MagicMock()
    mock_game_query.filter_by.return_value = mock_game_query
    mock_game_query.one_or_none.return_value = mock_game
    mock_context.db_session.query.return_value = mock_game_query
    
    # Execute
    pidoreg_cmd(mock_update, mock_context)
    
    # Verify player was appended to game.players
    assert mock_context.tg_user in mock_game.players
    
    # Verify db session was committed
    mock_context.db_session.commit.assert_called_once()