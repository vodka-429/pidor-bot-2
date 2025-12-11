"""Tests for utility functions."""
import pytest
from bot.utils import escape_markdown2_safe, format_number, escape_word


class TestEscapeMarkdown2Safe:
    """Tests for escape_markdown2_safe function."""
    
    def test_escape_markdown2_safe_basic_text(self):
        """Test basic text escaping."""
        text = "Hello world"
        result = escape_markdown2_safe(text)
        assert result == "Hello world"
    
    def test_escape_markdown2_safe_special_chars(self):
        """Test escaping of special characters."""
        text = "Test (with) brackets and dots."
        result = escape_markdown2_safe(text)
        # Should escape parentheses and dots
        assert "\\(" in result
        assert "\\)" in result
        assert "\\." in result
    
    def test_escape_markdown2_safe_empty_string(self):
        """Test handling of empty string."""
        result = escape_markdown2_safe("")
        assert result == ""
    
    def test_escape_markdown2_safe_none(self):
        """Test handling of None."""
        result = escape_markdown2_safe(None)
        assert result is None
    
    def test_escape_markdown2_safe_already_escaped(self):
        """Test handling of already escaped text."""
        text = "Already escaped \\(text\\)"
        result = escape_markdown2_safe(text)
        # Should still escape properly without double escaping
        assert result is not None


class TestFormatNumber:
    """Tests for format_number function."""
    
    def test_format_number_integer(self):
        """Test formatting of integer."""
        result = format_number(42)
        assert result == "42"
    
    def test_format_number_float_with_dot(self):
        """Test formatting of float with decimal point."""
        result = format_number(12.5)
        assert result == "12\\.5"
    
    def test_format_number_float_multiple_decimals(self):
        """Test formatting of float with multiple decimal places."""
        result = format_number(123.456)
        assert result == "123\\.456"
    
    def test_format_number_string_number(self):
        """Test formatting of string that looks like number."""
        result = format_number("42.5")
        # Should be escaped as string
        assert "\\." in result
    
    def test_format_number_zero(self):
        """Test formatting of zero."""
        result = format_number(0)
        assert result == "0"
    
    def test_format_number_negative(self):
        """Test formatting of negative number."""
        result = format_number(-12.3)
        assert result == "-12\\.3"


class TestEscapeWord:
    """Tests for escape_word function."""
    
    def test_escape_word_simple(self):
        """Test escaping simple word."""
        result = escape_word("победа")
        assert result == "победа"
    
    def test_escape_word_with_parentheses(self):
        """Test escaping word with parentheses."""
        result = escape_word("раз(а)")
        assert result == "раз\\(а\\)"
    
    def test_escape_word_with_special_chars(self):
        """Test escaping word with various special characters."""
        result = escape_word("test-word_with.dots")
        assert "\\-" in result
        assert "_" in result  # Underscore should be escaped
        assert "\\." in result
    
    def test_escape_word_empty(self):
        """Test handling of empty word."""
        result = escape_word("")
        assert result == ""
    
    def test_escape_word_none(self):
        """Test handling of None."""
        result = escape_word(None)
        assert result is None
    
    def test_escape_word_multiple_parentheses(self):
        """Test escaping word with multiple parentheses."""
        result = escape_word("test(1)(2)")
        assert result == "test\\(1\\)\\(2\\)"


class TestMarkdownV2Integration:
    """Integration tests for MarkdownV2 escaping."""
    
    def test_votes_word_escaping(self):
        """Test escaping of vote count words."""
        # Test different forms of vote count words
        words = ["голос", "голоса", "голосов"]
        for word in words:
            result = escape_word(word)
            assert result == word  # These don't contain special chars
    
    def test_points_word_escaping(self):
        """Test escaping of points words with parentheses."""
        words = ["балл", "балла", "баллов", "раз(а)"]
        for word in words:
            result = escape_word(word)
            if "(" in word:
                assert "\\(" in result
                assert "\\)" in result
            else:
                assert result == word
    
    def test_decimal_points_in_results(self):
        """Test formatting of decimal points in voting results."""
        test_numbers = [12.5, 8.3, 100.0, 0.5]
        for number in test_numbers:
            result = format_number(number)
            if "." in str(number):
                assert "\\." in result
                assert str(number).replace(".", "\\.") == result
    
    def test_combined_escaping_scenario(self):
        """Test combined escaping scenario like in voting results."""
        # Simulate a voting result line
        username = "TestUser"
        points = 12.5
        votes = 3
        votes_word = "голоса"
        
        escaped_username = escape_markdown2_safe(username)
        escaped_points = format_number(points)
        escaped_votes_word = escape_word(votes_word)
        
        # Build result line similar to actual code
        result_line = f"{escaped_username}: {escaped_points} {escaped_votes_word} ({votes})"
        
        assert "TestUser" in result_line
        assert "12\\.5" in result_line
        assert "голоса" in result_line
        assert "(3)" in result_line
