"""Тесты для вспомогательных функций тестового чата"""
import pytest
from unittest.mock import patch
from bot.handlers.game.voting_helpers import is_test_chat


@patch('bot.handlers.game.voting_helpers.get_test_chat_id')
def test_is_test_chat_returns_true_for_test_chat(mock_get_test_chat_id):
    """Проверяет, что функция возвращает True для тестового чата"""
    TEST_CHAT_ID = -4608252738
    mock_get_test_chat_id.return_value = TEST_CHAT_ID
    assert is_test_chat(TEST_CHAT_ID) is True


@patch('bot.handlers.game.voting_helpers.get_test_chat_id')
def test_is_test_chat_returns_false_for_other_chats(mock_get_test_chat_id):
    """Проверяет, что функция возвращает False для других чатов"""
    mock_get_test_chat_id.return_value = -4608252738
    assert is_test_chat(-123456789) is False
    assert is_test_chat(-987654321) is False


@patch('bot.handlers.game.voting_helpers.get_test_chat_id')
def test_is_test_chat_returns_false_for_positive_chat_id(mock_get_test_chat_id):
    """Проверяет обработку положительных ID"""
    mock_get_test_chat_id.return_value = -4608252738
    assert is_test_chat(123456789) is False
    assert is_test_chat(1) is False
