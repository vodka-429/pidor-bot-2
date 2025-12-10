"""Helper functions for custom voting functionality."""
import json
from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, User as TGUser
from bot.app.models import TGUser


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


def calculate_max_votes(missed_days: int) -> int:
    """
    Рассчитывает максимальное количество выборов на основе пропущенных дней.

    Формула:
    - Для четных чисел: количество_дней / 2
    - Для простых чисел: 1 выбор
    - Для составных нечетных чисел: количество_дней / наименьший_делитель

    Args:
        missed_days: Количество пропущенных дней

    Returns:
        Максимальное количество выборов для пользователя
    """
    # Преобразуем в int на случай, если передан MagicMock или другой объект
    try:
        missed_days = int(missed_days)
    except (TypeError, ValueError):
        return 1

    if missed_days <= 0:
        return 1

    # Для четных чисел - делим на 2
    if missed_days % 2 == 0:
        return missed_days // 2

    # Для нечетных чисел проверяем, является ли число простым
    def is_prime(n):
        if n < 2:
            return False
        for i in range(2, int(n ** 0.5) + 1):
            if n % i == 0:
                return False
        return True

    # Если простое число - возвращаем 1
    if is_prime(missed_days):
        return 1

    # Для составных нечетных чисел находим наименьший делитель
    for i in range(3, int(missed_days ** 0.5) + 1, 2):
        if missed_days % i == 0:
            return missed_days // i

    # Если не нашли делитель, возвращаем 1 (на всякий случай)
    return 1


def count_voters(votes_data: str) -> int:
    """
    Подсчитывает количество уникальных пользователей, которые проголосовали.

    Args:
        votes_data: JSON строка с данными голосов в формате {"user_id": [candidate_ids]}

    Returns:
        Количество уникальных пользователей, которые проголосовали
    """
    if not votes_data or votes_data == '{}':
        return 0

    try:
        votes = json.loads(votes_data)
        return len(votes)
    except (json.JSONDecodeError, TypeError):
        return 0


def format_player_with_wins(player: TGUser, wins: int) -> str:
    """
    Форматирует отображение игрока с количеством побед.

    Args:
        player: Объект TGUser
        wins: Количество побед

    Returns:
        Строка в формате "Имя Фамилия (N побед)"
    """
    # Формируем имя игрока
    player_name = player.first_name
    if player.last_name:
        player_name += f" {player.last_name}"

    # Формируем правильное склонение для "победа"
    if wins % 10 == 1 and wins % 100 != 11:
        wins_word = "победа"
    elif wins % 10 in [2, 3, 4] and wins % 100 not in [12, 13, 14]:
        wins_word = "победы"
    else:
        wins_word = "побед"

    return f"{player_name} ({wins} {wins_word})"


def get_player_weights(db_session, game_id: int, year: int) -> List[Tuple[TGUser, int]]:
    """
    Получает веса игроков (количество побед в году).

    Args:
        db_session: Сессия базы данных
        game_id: ID игры
        year: Год для подсчёта побед

    Returns:
        Список кортежей (TGUser, количество побед), отсортированный по убыванию побед
    """
    from sqlalchemy import func, text
    from sqlmodel import select
    from bot.app.models import TGUser, GameResult

    stmt = select(TGUser, func.count(GameResult.winner_id).label('count')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == game_id, GameResult.year == year) \
        .group_by(TGUser) \
        .order_by(text('count DESC'))

    return db_session.exec(stmt).all()


def format_weights_message(player_weights: List[Tuple[TGUser, int]], missed_count: int, max_votes: int = None) -> str:
    """
    Форматирует информационное сообщение с весами игроков для финального голосования.

    Args:
        player_weights: Список кортежей (TGUser, количество побед)
        missed_count: Количество пропущенных дней
        max_votes: Максимальное количество выборов (опционально)

    Returns:
        Отформатированное сообщение в формате Markdown V2
    """
    from bot.utils import escape_markdown2

    # Формируем список весов
    weights_list = []
    for player, weight in player_weights:
        weights_list.append(f"• {escape_markdown2(format_player_with_wins(player, weight))}")
    weights_text = '\n'.join(weights_list)

    # Формируем полное сообщение
    from bot.handlers.game.text_static import FINAL_VOTING_MESSAGE

    # Если max_votes не передан, рассчитываем его
    if max_votes is None:
        max_votes = calculate_max_votes(missed_count)

    return FINAL_VOTING_MESSAGE.format(
        missed_days=missed_count,
        player_weights=weights_text,
        max_votes=max_votes
    )


def duplicate_candidates_for_test(candidates: List[TGUser], chat_id: int, target_count: int = 30) -> List[TGUser]:
    """
    Дублирует кандидатов для тестового чата до достижения target_count.

    Args:
        candidates: Список оригинальных кандидатов
        chat_id: ID чата для проверки, является ли он тестовым
        target_count: Целевое количество кандидатов (по умолчанию 30)

    Returns:
        Список кандидатов (оригинальные + дубликаты для тестового чата)
    """
    from bot.handlers.game.commands import is_test_chat

    # Если это не тестовый чат или кандидатов уже достаточно, возвращаем как есть
    if not is_test_chat(chat_id) or len(candidates) >= target_count:
        return candidates

    # Создаем список с дубликатами
    result_candidates = list(candidates)  # Копируем оригинальных кандидатов

    # Дублируем кандидатов циклически до достижения target_count
    copy_number = 2
    while len(result_candidates) < target_count:
        for original_candidate in candidates:
            if len(result_candidates) >= target_count:
                break

            # Создаем копию объекта TGUser с модифицированным именем
            duplicate_candidate = TGUser(
                id=original_candidate.id,  # Важно: ID остается тот же для корректного подсчета голосов
                first_name=f"{original_candidate.first_name} (копия {copy_number})",
                last_name=original_candidate.last_name,
                username=original_candidate.username
            )
            result_candidates.append(duplicate_candidate)

        copy_number += 1

    return result_candidates


def create_voting_keyboard(candidates: List[TGUser], voting_id: int, votes_per_row: int = 2, user_votes: List[int] = None, chat_id: int = None, player_wins: dict = None) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопками для голосования за кандидатов.

    Args:
        candidates: Список кандидатов (TGUser объекты)
        voting_id: ID голосования для формирования callback_data
        votes_per_row: Количество кнопок в одном ряду (по умолчанию 2)
        user_votes: Список ID кандидатов, за которых уже проголосовал пользователь (опционально)
        chat_id: ID чата для дублирования кандидатов в тестовом чате (опционально)
        player_wins: Словарь {player_id: количество_побед} для отображения в кнопках (опционально)

    Returns:
        InlineKeyboardMarkup с кнопками кандидатов
    """
    # Дублируем кандидатов для тестового чата, если передан chat_id
    # if chat_id is not None:
    #     candidates = duplicate_candidates_for_test(candidates, chat_id)

    keyboard = []
    row = []

    # Если user_votes не передан, используем пустой список
    if user_votes is None:
        user_votes = []

    for candidate in candidates:
        # Формируем текст кнопки из имени пользователя
        button_text = candidate.first_name
        if candidate.last_name:
            button_text += f" {candidate.last_name}"
        
        # Добавляем количество побед в скобках, если информация доступна
        if player_wins and candidate.id in player_wins:
            wins_count = player_wins[candidate.id]
            button_text += f" ({wins_count})"

        # Добавляем ✅ если пользователь уже проголосовал за этого кандидата
        if candidate.id in user_votes:
            button_text = f"✅ {button_text}"

        # Создаём кнопку с callback_data, используя реальный voting_id
        button = InlineKeyboardButton(
            text=button_text,
            callback_data=format_vote_callback_data(voting_id, candidate.id)
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


def finalize_voting(final_voting, context, auto_vote_for_non_voters: bool = True) -> tuple:
    """
    Подсчитывает результаты финального голосования и создаёт записи GameResult.

    Args:
        final_voting: Объект FinalVoting с данными голосования
        context: Контекст бота с доступом к БД
        auto_vote_for_non_voters: Добавлять ли автоматические голоса за не проголосовавших

    Returns:
        Кортеж (winner: TGUser, results: Dict[int, Dict[str, int]])
        где results - словарь {candidate_id: {'weighted': int, 'votes': int}}
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
    # Обрабатываем как кортежи, так и объекты Row
    weights_dict = {}
    for row in player_weights_result:
        if isinstance(row, tuple) and len(row) == 2:
            user_id, weight = row
        else:
            # Если это объект Row, извлекаем значения по индексу
            user_id = row[0]
            weight = row[1]
        weights_dict[user_id] = weight

    # Добавляем автоматические голоса для не проголосовавших игроков
    if auto_vote_for_non_voters:
        # Получаем список всех игроков с весами
        all_player_ids = set(weights_dict.keys())

        # Определяем, кто уже проголосовал
        voted_player_ids = set(int(user_id) for user_id in votes_data.keys())

        # Находим не проголосовавших игроков
        non_voters = all_player_ids - voted_player_ids

        # Рассчитываем максимальное количество голосов для данного голосования
        max_votes = calculate_max_votes(final_voting.missed_days_count)

        # Для каждого не проголосовавшего игрока добавляем ВСЕ голоса за себя
        for player_id in non_voters:
            user_id_str = str(player_id)
            # Не проголосовавший игрок отдает ВСЕ свои голоса только за себя
            votes_data[user_id_str] = [player_id] * max_votes

    # Подсчитываем взвешенные голоса и реальные голоса для каждого кандидата
    results = {}

    for user_id_str, candidate_ids in votes_data.items():
        user_id = int(user_id_str)
        # Получаем вес голосующего (если игрок не имел побед, вес = 1)
        voter_weight = weights_dict.get(user_id, 1)

        # Рассчитываем вес одного голоса (вес голосующего делится на количество его выборов)
        votes_count = len(candidate_ids)
        if votes_count > 0:
            vote_weight = float(voter_weight) / votes_count
        else:
            vote_weight = 0.0

        # Добавляем взвешенный голос и реальный голос каждому кандидату
        for candidate_id in candidate_ids:
            if candidate_id not in results:
                results[candidate_id] = {'weighted': 0.0, 'votes': 0}
            results[candidate_id]['weighted'] += vote_weight
            results[candidate_id]['votes'] += 1

    # Определяем победителя с максимальным взвешенным результатом
    if not results:
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
        results[winner_id] = {'weighted': 0.0, 'votes': 0}
    else:
        winner_id = max(results, key=lambda x: results[x]['weighted'])

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

    return winner, results
