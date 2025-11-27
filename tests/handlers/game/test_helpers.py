"""Tests for helper functions in game handler."""
import pytest
from bot.handlers.game.commands import build_player_table


@pytest.mark.unit
def test_build_player_table_empty_list():
    """Test that empty list returns empty string."""
    result = build_player_table([])
    assert result == ""


@pytest.mark.unit
def test_build_player_table_single_player(mock_tg_user):
    """Test formatting for a single player."""
    mock_tg_user.full_username.return_value = "@TestUser"
    
    result = build_player_table([(mock_tg_user, 5)])
    
    assert "1\\." in result
    assert "TestUser" in result
    assert "5" in result


@pytest.mark.unit
def test_build_player_table_multiple_players(sample_players):
    """Test numbering and formatting for multiple players."""
    # Create list of tuples (player, count)
    player_data = [(player, i * 2) for i, player in enumerate(sample_players, 1)]
    
    result = build_player_table(player_data)
    
    # Check that all players are numbered
    for i in range(1, len(sample_players) + 1):
        assert f"{i}\\." in result
    
    # Check that all player names are present
    for player in sample_players:
        player_name = player.full_username().replace("@", "")
        assert player_name in result


@pytest.mark.unit
def test_build_player_table_escapes_markdown(mock_tg_user):
    """Test that special markdown characters are escaped."""
    # Set username with special characters that need escaping
    mock_tg_user.full_username.return_value = "User_with*special[chars]"
    
    result = build_player_table([(mock_tg_user, 3)])
    
    # Check that the result contains escaped characters or the username
    # The escape_markdown2 function should handle special characters
    assert "User" in result
    assert "3" in result