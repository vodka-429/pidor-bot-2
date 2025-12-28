"""Тесты для вспомогательных функций тестового чата"""
import pytest
from bot.handlers.game.voting_helpers import is_test_chat, TEST_CHAT_ID


def test_is_test_chat_returns_true_for_test_chat():
    """Проверяет, что функция возвращает True для тестового чата"""
    assert is_test_chat(TEST_CHAT_ID) is True


def test_is_test_chat_returns_false_for_other_chats():
    """Проверяет, что функция возвращает False для других чатов"""
    assert is_test_chat(-123456789) is False
    assert is_test_chat(-987654321) is False


def test_is_test_chat_returns_false_for_positive_chat_id():
    """Проверяет обработку положительных ID"""
    assert is_test_chat(123456789) is False
    assert is_test_chat(1) is False
