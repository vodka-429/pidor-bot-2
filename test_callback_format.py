#!/usr/bin/env python3
"""Тестовый скрипт для проверки формата callback_data"""

from bot.handlers.game.voting_helpers import format_vote_callback_data, parse_vote_callback_data

# Тестируем формирование callback_data
voting_id = 1
candidate_id = 12345

callback_data = format_vote_callback_data(voting_id, candidate_id)
print(f"Generated callback_data: {callback_data}")

# Тестируем парсинг
try:
    parsed_voting_id, parsed_candidate_id = parse_vote_callback_data(callback_data)
    print(f"Parsed: voting_id={parsed_voting_id}, candidate_id={parsed_candidate_id}")
    print("✅ Format is correct!")
except ValueError as e:
    print(f"❌ Error parsing: {e}")

# Проверяем, что pattern совпадает
import re
pattern = r'^vote_'
if re.match(pattern, callback_data):
    print(f"✅ Pattern '{pattern}' matches callback_data")
else:
    print(f"❌ Pattern '{pattern}' does NOT match callback_data")
