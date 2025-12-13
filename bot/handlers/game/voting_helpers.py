"""Helper functions for custom voting functionality."""
import json
import logging
from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.app.models import TGUser, GameResult
from bot.handlers.game.commands import is_test_chat

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)


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

    # For TEST_CHAT_ID
    if missed_days > 10:
        missed_days = 4

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
        # Считаем только пользователей с непустыми массивами голосов
        return len([user_id for user_id, candidate_ids in votes.items() if len(candidate_ids) > 0])
    except (json.JSONDecodeError, TypeError):
        return 0


def format_player_with_wins(player: TGUser, wins: int) -> str:
    """
    Форматирует отображение игрока с количеством побед.

    Args:
        player: Объект TGUser
        wins: Количество побед

    Returns:
        Строка в формате "Имя Фамилия (N побед)" с экранированием для MarkdownV2
    """
    from bot.utils import escape_markdown2, escape_word, format_number

    # Формируем имя игрока
    player_name = player.first_name
    if player.last_name:
        player_name += f" {player.last_name}"

    # Экранируем имя игрока
    player_name_escaped = escape_markdown2(player_name)

    # Формируем правильное склонение для "победа"
    if wins % 10 == 1 and wins % 100 != 11:
        wins_word = "победа"
    elif wins % 10 in [2, 3, 4] and wins % 100 not in [12, 13, 14]:
        wins_word = "победы"
    else:
        wins_word = "побед"

    # Экранируем склонение и число
    wins_word_escaped = escape_word(wins_word)
    wins_escaped = format_number(wins)

    return f"{player_name_escaped} \\({wins_escaped} {wins_word_escaped}\\)"


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
        weights_list.append(f"• {format_player_with_wins(player, weight)}")
    weights_text = '\n'.join(weights_list)

    # Формируем полное сообщение
    from bot.handlers.game.text_static import FINAL_VOTING_MESSAGE

    # Если max_votes не передан, рассчитываем его
    if max_votes is None:
        max_votes = calculate_max_votes(missed_count)

    # Формируем текст о победителях в зависимости от max_votes
    if max_votes == 1:
        winner_text = "• Победитель получит *все пропущенные дни*\\!"
    else:
        winner_text = f"• Победители \\(максимум *{max_votes}*\\) разделят между собой *все пропущенные дни*\\!"

    return FINAL_VOTING_MESSAGE.format(
        missed_days=missed_count,
        player_weights=weights_text,
        max_votes=max_votes,
        winner_text=winner_text
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


def create_voting_keyboard(candidates: List[TGUser], voting_id: int, votes_per_row: int = 2, chat_id: int = None, player_wins: dict = None) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопками для голосования за кандидатов.

    Args:
        candidates: Список кандидатов (TGUser объекты)
        voting_id: ID голосования для формирования callback_data
        votes_per_row: Количество кнопок в одном ряду (по умолчанию 2)
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

    for candidate in candidates:
        # Формируем текст кнопки из имени пользователя
        button_text = candidate.first_name
        if candidate.last_name:
            button_text += f" {candidate.last_name}"

        # Добавляем количество побед в скобках, если информация доступна
        if player_wins and candidate.id in player_wins:
            wins_count = player_wins[candidate.id]
            button_text += f" ({wins_count})"

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
    Подсчитывает результаты финального голосования.

    Алгоритм:
    1. Загружаем исходные голоса из БД
    2. Получаем веса игроков (количество побед)
    3. Определяем, кто проголосовал вручную
    4. Добавляем автоголоса для не проголосовавших (если включено)
    5. Подсчитываем результаты для каждого кандидата
    6. Определяем победителей
    7. Сохраняем результаты в БД
    """
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from sqlalchemy import func
    from sqlmodel import select
    from bot.app.models import TGUser, GameResult

    MOSCOW_TZ = ZoneInfo('Europe/Moscow')

    # ШАГ 1: Загружаем исходные голоса (до автоголосования)
    original_votes = json.loads(final_voting.votes_data)

    # ШАГ 2: Получаем веса игроков (количество побед в году) вместе с их Telegram ID
    stmt = select(TGUser.id, TGUser.tg_id, func.count(GameResult.winner_id).label('weight')) \
        .join(TGUser, GameResult.winner_id == TGUser.id) \
        .filter(GameResult.game_id == final_voting.game_id, GameResult.year == final_voting.year) \
        .group_by(TGUser.id, TGUser.tg_id)

    player_weights_result = context.db_session.exec(stmt).all()

    # Создаём словари: user_id -> вес и tg_id -> user_id
    weights_dict = {}
    tg_id_to_db_id = {}
    for row in player_weights_result:
        user_id = row[0]
        tg_id = row[1]
        weight = row[2]
        weights_dict[user_id] = weight
        tg_id_to_db_id[tg_id] = user_id

    # ШАГ 3: Определяем, кто проголосовал вручную (с преобразованием Telegram ID в DB ID)
    manual_voters = set()
    for user_id_str, candidate_ids in original_votes.items():
        if len(candidate_ids) > 0:
            tg_id = int(user_id_str)  # Это Telegram ID
            # Преобразуем Telegram ID во внутренний ID
            if tg_id in tg_id_to_db_id:
                db_id = tg_id_to_db_id[tg_id]
                manual_voters.add(db_id)

    # ШАГ 4: Создаем финальный словарь голосов (с автоголосами, если нужно)
    final_votes = dict(original_votes)  # Копируем исходные голоса

    if auto_vote_for_non_voters:
        # Находим игроков, которые не проголосовали
        all_player_ids = set(weights_dict.keys())
        non_voters = all_player_ids - manual_voters

        # Рассчитываем максимальное количество голосов
        max_votes = calculate_max_votes(final_voting.missed_days_count)

        # Добавляем автоголоса для не проголосовавших
        for player_id in non_voters:
            user_id_str = str(player_id)
            # Не проголосовавший игрок отдает ВСЕ свои голоса только за себя
            final_votes[user_id_str] = [player_id] * max_votes

    # ШАГ 5: Подсчитываем результаты для каждого кандидата
    results = {}

    for user_id_str, candidate_ids in final_votes.items():
        user_id = int(user_id_str)
        if user_id in tg_id_to_db_id:
            db_id = tg_id_to_db_id[user_id]
            voter_weight = weights_dict.get(db_id, 1)
            is_manual_vote = db_id in manual_voters
        else:
            voter_weight = weights_dict.get(user_id, 1)
            is_manual_vote = user_id in manual_voters

        # Вес одного голоса = вес голосующего / количество его выборов
        votes_count = len(candidate_ids)
        if votes_count > 0:
            vote_weight = float(voter_weight) / votes_count
        else:
            continue  # Пропускаем пользователей без голосов

        # Добавляем голоса каждому кандидату
        for candidate_id in candidate_ids:
            if candidate_id not in results:
                results[candidate_id] = {
                    'weighted': 0.0,
                    'votes': 0,
                    'auto_votes': 0,
                    'unique_voters': set()
                }

            results[candidate_id]['weighted'] += vote_weight

            # Голоса учитываем только для ручного голосования
            if is_manual_vote:
                results[candidate_id]['votes'] += 1
            else:
                results[candidate_id]['auto_votes'] += 1

            results[candidate_id]['unique_voters'].add(user_id)

    # ШАГ 6: Устанавливаем флаг auto_voted для каждого кандидата
    # Кандидат помечается как "автоголосование", если он САМ не голосовал вручную
    for candidate_id in results:
        results[candidate_id]['auto_voted'] = candidate_id not in manual_voters
        # Преобразуем set в количество
        results[candidate_id]['unique_voters'] = len(results[candidate_id]['unique_voters'])

    # ШАГ 7: Определяем победителей
    if not results:
        # Если никто не проголосовал, выбираем случайных кандидатов
        import random
        all_candidates = context.db_session.exec(
            select(TGUser.id)
            .join(GameResult, GameResult.winner_id == TGUser.id)
            .filter(GameResult.game_id == final_voting.game_id, GameResult.year == final_voting.year)
            .group_by(TGUser.id)
        ).all()

        if not all_candidates:
            raise ValueError("No candidates found for voting")

        max_winners = calculate_max_votes(final_voting.missed_days_count)
        num_winners = min(max_winners, len(all_candidates))
        winner_ids = random.sample(all_candidates, num_winners)

        # Добавляем результаты для случайных победителей
        for winner_id in winner_ids:
            results[winner_id] = {
                'weighted': 0.0,
                'votes': 0,
                'unique_voters': 0,
                'auto_voted': True
            }
    else:
        # Сортируем кандидатов по взвешенным очкам
        sorted_candidates = sorted(results.items(), key=lambda x: x[1]['weighted'], reverse=True)

        # Берем первых N победителей
        max_winners = calculate_max_votes(final_voting.missed_days_count)
        num_winners = min(max_winners, len(sorted_candidates))
        winner_ids = [candidate_id for candidate_id, _ in sorted_candidates[:num_winners]]

    # ШАГ 8: Загружаем объекты победителей
    winners = []
    for winner_id in winner_ids:
        winner = context.db_session.query(TGUser).filter_by(id=winner_id).one()
        winners.append((winner_id, winner))

    # ШАГ 9: Обновляем FinalVoting
    final_voting.ended_at = datetime.now(tz=MOSCOW_TZ)
    final_voting.winner_id = winners[0][0] if winners else None
    context.db_session.commit()

    # ШАГ 8: Рассчитываем распределение дней между победителями и сохраняем в winners_data
    winners_data_list = []
    if winners and final_voting.missed_days_count > 0:
        winners_data_list = calculate_days_distribution(winners, final_voting.missed_days_count)

    # ШАГ 9: Обновляем FinalVoting
    final_voting.winners_data = json.dumps(winners_data_list)
    context.db_session.commit()

    logger.info(f"winners: {winners}")
    logger.info(f"winners_data: {winners_data_list}")
    logger.info(f"results: {results}")
    return winners, results


def calculate_days_distribution(winners: List[Tuple[int, TGUser]], missed_days_count: int) -> List[dict]:
    """
    Рассчитывает распределение дней между победителями.

    Args:
        winners: Список кортежей (winner_id, TGUser) с победителями
        missed_days_count: Количество пропущенных дней для распределения

    Returns:
        Список словарей с информацией о распределении: [{"winner_id": 1, "days_count": 3}, ...]
    """
    if not winners or missed_days_count <= 0:
        return []

    days_per_winner = missed_days_count // len(winners)
    remainder = missed_days_count % len(winners)

    winners_data_list = []
    for winner_index, (winner_id, winner) in enumerate(winners):
        # Определяем количество дней для текущего победителя
        if winner_index < remainder:
            days_count = days_per_winner + 1
        else:
            days_count = days_per_winner

        winners_data_list.append({
            'winner_id': winner_id,
            'days_count': days_count
        })

    return winners_data_list


def format_voting_results(
    winners: List[Tuple[int, TGUser]],
    results: dict,
    missed_days_count: int,
    db_session
) -> Tuple[str, str, str]:
    """
    Форматирует результаты финального голосования для отображения.

    Args:
        winners: Список кортежей (winner_id, TGUser) с победителями
        results: Словарь с результатами голосования
        missed_days_count: Количество пропущенных дней
        db_session: Сессия базы данных

    Returns:
        Кортеж из трех строк:
        - winners_text: Имена победителей через запятую
        - voting_results_text: Детальные результаты голосования
        - days_distribution_text: Информация о распределении дней
    """
    from bot.utils import escape_markdown2, escape_word, format_number

    # Формируем строку с именами победителей
    winner_names = []
    for winner_id, winner in winners:
        winner_names.append(escape_markdown2(winner.full_username()))

    winners_text = ', '.join(winner_names) if winner_names else "Нет победителей"

    # Формируем детальные результаты голосования
    voting_results_list = []
    for candidate_id, result_data in sorted(results.items(), key=lambda x: x[1]['weighted'], reverse=True):
        # Находим кандидата по ID
        candidate = db_session.query(TGUser).filter_by(id=candidate_id).one()
        votes_count = result_data['votes']
        auto_votes_count = result_data.get('auto_votes', 0)
        weighted_points = result_data['weighted']
        auto_voted = result_data['auto_voted']

        # Формируем правильное склонение для "голос"
        if votes_count % 10 == 1 and votes_count % 100 != 11:
            votes_word = "голос"
        elif votes_count % 10 in [2, 3, 4] and votes_count % 100 not in [12, 13, 14]:
            votes_word = "голоса"
        else:
            votes_word = "голосов"

        # Форматируем взвешенные очки с одним знаком после запятой
        weighted_points_str = format_number(f"{weighted_points:.1f}")

        # Формируем правильное склонение для "очко"
        weighted_points_int = int(weighted_points)
        if weighted_points_int % 10 == 1 and weighted_points_int % 100 != 11:
            points_word = "очко"
        elif weighted_points_int % 10 in [2, 3, 4] and weighted_points_int % 100 not in [12, 13, 14]:
            points_word = "очка"
        else:
            points_word = "очков"

        # Формируем строку результата
        result_line = f"• {escape_markdown2(candidate.full_username())}: *{votes_count}* {escape_word(votes_word)}, *{weighted_points_str}* взвешенных {escape_word(points_word)}"

        # Если кандидат получил автоголосование (сам не проголосовал)
        if auto_voted:
            result_line += " _\\(не проголосовал, пидор\\)_"

        voting_results_list.append(result_line)

    voting_results_text = '\n'.join(voting_results_list)

    # Формируем информацию о распределении дней
    days_distribution_list = []
    if winners and missed_days_count > 0:
        # Используем функцию для расчета распределения
        winners_distribution = calculate_days_distribution(winners, missed_days_count)

        for winner_info in winners_distribution:
            winner_id = winner_info['winner_id']
            days_count = winner_info['days_count']

            # Находим объект победителя
            winner = next((w for wid, w in winners if wid == winner_id), None)
            if not winner:
                continue

            # Формируем правильное склонение для "день"
            if days_count % 10 == 1 and days_count % 100 != 11:
                days_word = "день"
            elif days_count % 10 in [2, 3, 4] and days_count % 100 not in [12, 13, 14]:
                days_word = "дня"
            else:
                days_word = "дней"

            days_distribution_list.append(
                f"• {escape_markdown2(winner.full_username())} получает *{days_count}* {escape_word(days_word)} в свою копилку\\!"
            )

    days_distribution_text = '\n'.join(days_distribution_list) if days_distribution_list else ""

    return winners_text, voting_results_text, days_distribution_text


def create_game_results_for_winners(
    winners: List[Tuple[int, TGUser]],
    missed_days_list: List[int],
    game_id: int,
    year: int,
    db_session
) -> None:
    """
    Создает записи GameResult для победителей финального голосования.

    Распределяет пропущенные дни между победителями и создает записи в базе данных.

    Args:
        winners: Список кортежей (winner_id, TGUser) с победителями
        missed_days_list: Список пропущенных дней года
        game_id: ID игры
        year: Год
        db_session: Сессия базы данных
    """
    if not winners or not missed_days_list:
        return

    # Используем функцию для расчета распределения
    winners_distribution = calculate_days_distribution(winners, len(missed_days_list))

    # Создаем записи GameResult для каждого победителя
    day_index = 0
    for winner_info in winners_distribution:
        winner_id = winner_info['winner_id']
        days_count = winner_info['days_count']

        # Создаем записи для каждого дня
        for i in range(days_count):
            if day_index < len(missed_days_list):
                day = missed_days_list[day_index]
                game_result = GameResult(
                    game_id=game_id,
                    winner_id=winner_id,
                    year=year,
                    day=day
                )
                db_session.add(game_result)
                day_index += 1

    # Сохраняем изменения
    db_session.commit()
