"""Helper functions for custom voting functionality."""
from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, User as TGUser


# Константа для идентификации callback голосования
VOTE_CALLBACK_PREFIX = 'vote_'


def format_vote_callback_data(voting_id: int, candidate_id: int) -> str:
    """
    Форматирует callback_data для кнопки голосования.

    Args:
        voting_id: ID голосования
        candidate_id: ID кандидата

    Returns:
        Строка в формате 'vote_{voting_id}_{candidate_id}'
    """
    return f"{VOTE_CALLBACK_PREFIX}{voting_id}_{candidate_id}"


def parse_vote_callback_data(callback_data: str) -> Tuple[int, int]:
    """
    Парсит callback_data для получения voting_id и candidate_id.

    Args:
        callback_data: Строка callback_data в формате 'vote_{voting_id}_{candidate_id}'

    Returns:
        Кортеж (voting_id, candidate_id)

    Raises:
        ValueError: Если формат callback_data некорректен
    """
    if not callback_data.startswith(VOTE_CALLBACK_PREFIX):
        raise ValueError(f"Invalid callback_data format: {callback_data}")

    # Убираем префикс и разделяем по '_'
    data = callback_data[len(VOTE_CALLBACK_PREFIX):]
    parts = data.split('_')

    if len(parts) != 2:
        raise ValueError(f"Invalid callback_data format: {callback_data}")

    try:
        voting_id = int(parts[0])
        candidate_id = int(parts[1])
    except ValueError as e:
        raise ValueError(f"Invalid callback_data format: {callback_data}") from e

    return voting_id, candidate_id


def create_voting_keyboard(candidates: List[TGUser], votes_per_row: int = 2) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопками для голосования за кандидатов.

    Args:
        candidates: Список кандидатов (TGUser объекты)
        votes_per_row: Количество кнопок в одном ряду (по умолчанию 2)

    Returns:
        InlineKeyboardMarkup с кнопками кандидатов
    """
    keyboard = []
    row = []

    for candidate in candidates:
        # Формируем текст кнопки из имени пользователя
        button_text = candidate.first_name
        if candidate.last_name:
            button_text += f" {candidate.last_name}"

        # Создаём кнопку с callback_data
        # Используем candidate.id для voting_id (будет заменено при использовании)
        # и candidate.id для candidate_id
        button = InlineKeyboardButton(
            text=button_text,
            callback_data=f"vote_{{voting_id}}_{candidate.id}"
        )

        row.append(button)

        # Если ряд заполнен, добавляем его в клавиатуру
        if len(row) >= votes_per_row:
            keyboard.append(row)
            row = []

    # Добавляем оставшиеся кнопки
    if row:
        keyboard.append(row)

    return InlineKeyboardMarkup(keyboard)


def finalize_voting(final_voting, context) -> tuple:
    """
    Подсчитывает результаты финального голосования и создаёт записи GameResult.

    Args:
        final_voting: Объект FinalVoting с данными голосования
        context: Контекст бота с доступом к БД

    Returns:
        Кортеж (winner: TGUser, weighted_votes: Dict[int, int])
        где weighted_votes - словарь {candidate_id: weighted_vote_count}
    """
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from sqlalchemy import func, text
    from sqlmodel import select
    from bot.app.models import TGUser, GameResult

    MOSCOW_TZ = ZoneInfo('Europe/Moscow')

    # Загружаем голоса из votes_data
    votes_data = json.loads(final_voting.votes_data)

    # Получаем веса игроков (количество побед в году)
    stmt = select(TGUser.id, func.count(GameResult.winner_id).label('weight')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == final_voting.game_id, GameResult.year == final_voting.year) \
        .group_by(TGUser.id)

    player_weights_result = context.db_session.exec(stmt).all()

    # Создаём словарь: user_id -> вес
    weights_dict = {user_id: weight for user_id, weight in player_weights_result}

    # Подсчитываем взвешенные голоса для каждого кандидата
    weighted_votes = {}

    for user_id_str, candidate_ids in votes_data.items():
        user_id = int(user_id_str)
        # Получаем вес голосующего (если игрок не имел побед, вес = 1)
        voter_weight = weights_dict.get(user_id, 1)

        # Добавляем взвешенный голос каждому кандидату
        for candidate_id in candidate_ids:
            if candidate_id not in weighted_votes:
                weighted_votes[candidate_id] = 0
            weighted_votes[candidate_id] += voter_weight

    # Определяем победителя с максимальным взвешенным результатом
    if not weighted_votes:
        # Если никто не проголосовал, выбираем случайного кандидата
        import random
        all_candidates = context.db_session.exec(
            select(TGUser.id)
            .join(GameResult, GameResult.winner_id == TGUser.id)
            .filter(GameResult.game_id == final_voting.game_id, GameResult.year == final_voting.year)
            .group_by(TGUser.id)
        ).all()
        winner_id = random.choice(all_candidates) if all_candidates else None
        if winner_id is None:
            raise ValueError("No candidates found for voting")
        weighted_votes[winner_id] = 0
    else:
        winner_id = max(weighted_votes, key=weighted_votes.get)

    # Загружаем объект победителя
    winner = context.db_session.query(TGUser).filter_by(id=winner_id).one()

    # Получаем список пропущенных дней
    missed_days = json.loads(final_voting.missed_days_list)

    # Создаём записи GameResult для всех пропущенных дней
    # TODO: enable it
    # for day_num in missed_days:
    #     game_result = GameResult(
    #         game_id=final_voting.game_id,
    #         year=final_voting.year,
    #         day=day_num,
    #         winner_id=winner.id
    #     )
    #     context.db_session.add(game_result)

    # Обновляем FinalVoting: устанавливаем ended_at и winner_id
    final_voting.ended_at = datetime.now(tz=MOSCOW_TZ)
    final_voting.winner_id = winner.id
    context.db_session.commit()

    return winner, weighted_votes
