"""Helper functions for custom voting functionality."""
import json
import logging
from typing import List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from bot.app.models import TGUser, GameResult
from bot.handlers.game.commands import is_test_chat
from bot.utils import escape_markdown2

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


def get_year_leaders(player_weights: List[Tuple[TGUser, int]]) -> List[Tuple[TGUser, int]]:
    """
    Определяет всех лидеров года (игроков с максимальным количеством побед).

    Args:
        player_weights: Список кортежей (TGUser, количество побед), отсортированный по убыванию побед

    Returns:
        Список кортежей (TGUser, количество побед) только для игроков с максимальным количеством побед
    """
    if not player_weights:
        return []

    # Получаем максимальное количество побед (первый элемент списка)
    max_wins = player_weights[0][1]

    # Фильтруем список, оставляя только игроков с максимальным количеством побед
    leaders = [(player, wins) for player, wins in player_weights if wins == max_wins]

    return leaders


def format_weights_message(player_weights: List[Tuple[TGUser, int]], missed_count: int, max_votes: int = None, excluded_leaders: List[Tuple[TGUser, int]] = None) -> str:
    """
    Форматирует информационное сообщение с весами игроков для финального голосования.

    Args:
        player_weights: Список кортежей (TGUser, количество побед)
        missed_count: Количество пропущенных дней
        max_votes: Максимальное количество выборов (опционально)
        excluded_leaders: Список кортежей (TGUser, количество побед) исключенных лидеров (опционально)

    Returns:
        Отформатированное сообщение в формате Markdown V2
    """
    from bot.utils import escape_markdown2

    # Формируем список весов
    weights_list = []
    for player, weight in player_weights:
        weights_list.append(f"• {format_player_with_wins(player, weight)}")
    weights_text = '\n'.join(weights_list)

    # Формируем информацию об исключенных лидерах
    excluded_leaders_info = ""
    if excluded_leaders:
        excluded_names = []
        for leader, wins in excluded_leaders:
            leader_name = leader.first_name
            if leader.last_name:
                leader_name += f" {leader.last_name}"
            excluded_names.append(f"❌ {escape_markdown2(leader_name)} НЕ УЧАСТВУЕТ \\(лидер года\\)")
        excluded_leaders_info = '\n'.join(excluded_names)

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
        excluded_leaders_info=excluded_leaders_info,
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


def format_button_text(candidate: TGUser, wins_count: int = None) -> str:
    """
    Форматирует текст кнопки для голосования.

    Args:
        candidate: Объект TGUser
        wins_count: Количество побед (опционально)

    Returns:
        Текст кнопки без экранирования (кнопки Telegram не поддерживают MarkdownV2)
    """
    # Формируем текст кнопки из имени пользователя
    button_text = candidate.first_name
    if candidate.last_name:
        button_text += f" {candidate.last_name}"

    # Добавляем количество побед в скобках, если информация доступна
    if wins_count is not None:
        button_text += f" ({wins_count})"

    # Возвращаем текст без экранирования, так как кнопки Telegram не поддерживают MarkdownV2
    return button_text


def create_voting_keyboard(candidates: List[TGUser], voting_id: int, votes_per_row: int = 2, chat_id: int = None, player_wins: dict = None, excluded_players: List[int] = None) -> InlineKeyboardMarkup:
    """
    Создаёт клавиатуру с кнопками для голосования за кандидатов.

    Args:
        candidates: Список кандидатов (TGUser объекты)
        voting_id: ID голосования для формирования callback_data
        votes_per_row: Количество кнопок в одном ряду (по умолчанию 2)
        chat_id: ID чата для дублирования кандидатов в тестовом чате (опционально)
        player_wins: Словарь {player_id: количество_побед} для отображения в кнопках (опционально)
        excluded_players: Список ID игроков, которые должны быть исключены из клавиатуры (опционально)

    Returns:
        InlineKeyboardMarkup с кнопками кандидатов
    """
    # Дублируем кандидатов для тестового чата, если передан chat_id
    # if chat_id is not None:
    #     candidates = duplicate_candidates_for_test(candidates, chat_id)

    # Фильтруем кандидатов, исключая указанных игроков
    if excluded_players:
        filtered_candidates = [c for c in candidates if c.id not in excluded_players]
    else:
        filtered_candidates = candidates

    keyboard = []
    row = []

    for candidate in filtered_candidates:
        # Получаем количество побед, если информация доступна
        wins_count = None
        if player_wins and candidate.id in player_wins:
            wins_count = player_wins[candidate.id]

        # Формируем экранированный текст кнопки
        button_text = format_button_text(candidate, wins_count)

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


def _select_random_winners(context, game_id: int, year: int, excluded_player_ids: List[int], max_winners: int, results: dict) -> List[int]:
    """
    Выбирает случайных победителей из всех игроков года, исключая указанных.

    Args:
        context: Контекст приложения
        game_id: ID игры
        year: Год
        excluded_player_ids: Список ID игроков для исключения
        max_winners: Максимальное количество победителей
        results: Словарь результатов для обновления

    Returns:
        Список ID победителей
    """
    import random
    from sqlmodel import select
    from bot.app.models import TGUser, GameResult

    all_candidates = context.db_session.exec(
        select(TGUser.id)
        .join(GameResult, GameResult.winner_id == TGUser.id)
        .filter(GameResult.game_id == game_id, GameResult.year == year)
        .group_by(TGUser.id)
    ).all()

    if not all_candidates:
        raise ValueError("No candidates found for voting")

    eligible_candidates = [c for c in all_candidates if c not in excluded_player_ids]

    if not eligible_candidates:
        raise ValueError("No eligible candidates found after exclusions")

    num_winners = min(max_winners, len(eligible_candidates))
    winner_ids = random.sample(eligible_candidates, num_winners)

    # Добавляем результаты для случайных победителей, если их еще нет
    for winner_id in winner_ids:
        if winner_id not in results:
            results[winner_id] = {
                'weighted': 0.0,
                'votes': 0,
                'unique_voters': 0,
                'auto_voted': True
            }

    return winner_ids


def finalize_voting(final_voting, context, auto_vote_for_non_voters: bool = True, excluded_player_ids: List[int] = None) -> tuple:
    """
    Подсчитывает результаты финального голосования.

    Алгоритм:
    1. Загружаем исходные голоса из БД
    2. Получаем веса игроков (количество побед)
    3. Определяем, кто проголосовал вручную
    4. Добавляем автоголоса для не проголосовавших (если включено)
    5. Подсчитываем результаты для каждого кандидата
    6. Определяем победителей (исключая указанных игроков)
    7. Сохраняем результаты в БД

    Args:
        final_voting: Объект финального голосования
        context: Контекст приложения
        auto_vote_for_non_voters: Включить автоголосование для не проголосовавших
        excluded_player_ids: Список ID игроков, которые должны быть исключены из победителей.
                            Эти игроки могут голосовать (их голоса учитываются с полным весом),
                            но ни один из них не может быть выбран победителем.
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

    if excluded_player_ids is None:
        excluded_player_ids = []

    if auto_vote_for_non_voters:
        # Находим игроков, которые не проголосовали
        all_player_ids = set(weights_dict.keys())
        non_voters = all_player_ids - manual_voters
        # Исключаем лидеров
        non_voters = non_voters - set(excluded_player_ids)

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

    # ШАГ 7: Определяем победителей (исключая указанных игроков)
    max_winners = calculate_max_votes(final_voting.missed_days_count)

    if not results:
        # Если никто не проголосовал, выбираем случайных кандидатов
        winner_ids = _select_random_winners(
            context, final_voting.game_id, final_voting.year,
            excluded_player_ids, max_winners, results
        )
    else:
        # Сортируем кандидатов по взвешенным очкам
        sorted_candidates = sorted(results.items(), key=lambda x: x[1]['weighted'], reverse=True)

        # Фильтруем исключенных игроков из списка кандидатов
        eligible_candidates = [(candidate_id, data) for candidate_id, data in sorted_candidates
                               if candidate_id not in excluded_player_ids]

        if not eligible_candidates:
            # Если нет подходящих кандидатов с голосами, выбираем случайных
            winner_ids = _select_random_winners(
                context, final_voting.game_id, final_voting.year,
                excluded_player_ids, max_winners, results
            )
        else:
            # Берем первых N победителей из оставшихся кандидатов
            num_winners = min(max_winners, len(eligible_candidates))
            winner_ids = [candidate_id for candidate_id, _ in eligible_candidates[:num_winners]]

    # ШАГ 8: Загружаем объекты победителей
    winners = []
    for winner_id in winner_ids:
        winner = context.db_session.query(TGUser).filter_by(id=winner_id).one()
        winners.append((winner_id, winner))

    # ШАГ 9: Обновляем FinalVoting
    final_voting.ended_at = datetime.now(tz=MOSCOW_TZ)
    final_voting.winner_id = winners[0][0] if winners else None
    context.db_session.commit()

    # ШАГ 8: Рассчитываем распределение дней между победителями с использованием пропорционального распределения
    winners_data_list = []
    if winners and final_voting.missed_days_count > 0:
        # Подготавливаем данные для пропорционального распределения
        winners_scores = []
        for winner_id, winner in winners:
            weighted_score = results[winner_id]['weighted']
            winners_scores.append((winner_id, winner, weighted_score))

        # Используем пропорциональное распределение
        proportional_distribution = distribute_days_proportionally(winners_scores, final_voting.missed_days_count)

        # Преобразуем результат в формат winners_data
        winners_data_list = []
        for winner_id, winner, days_count in proportional_distribution:
            winners_data_list.append({
                'winner_id': winner_id,
                'days_count': days_count
            })

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


def distribute_days_proportionally(winners_scores: List[Tuple[int, TGUser, float]], total_days: int) -> List[Tuple[int, TGUser, int]]:
    """
    Распределяет дни пропорционально взвешенным очкам победителей.

    Алгоритм:
    1. Рассчитать точные доли для каждого победителя: (score / total_score) * total_days
    2. Округлить вниз все значения и сохранить дробные части
    3. Распределить остаток дней победителям с наибольшими дробными частями
    4. Гарантировать, что сумма распределенных дней равна total_days

    Args:
        winners_scores: Список кортежей (winner_id, TGUser, weighted_score)
        total_days: Общее количество дней для распределения

    Returns:
        Список кортежей (winner_id, TGUser, days_count)
    """
    if not winners_scores or total_days <= 0:
        return []

    # Рассчитываем сумму взвешенных очков
    total_score = sum(score for _, _, score in winners_scores)

    if total_score == 0:
        # Если все очки равны 0, распределяем равномерно
        days_per_winner = total_days // len(winners_scores)
        remainder = total_days % len(winners_scores)

        result = []
        for i, (winner_id, user, _) in enumerate(winners_scores):
            days_count = days_per_winner + (1 if i < remainder else 0)
            result.append((winner_id, user, days_count))

        return result

    # Рассчитываем точные доли для каждого победителя
    exact_days = [(winner_id, user, (score / total_score) * total_days)
                  for winner_id, user, score in winners_scores]

    # Округляем вниз и сохраняем дробную часть
    floored_days = [(winner_id, user, int(days), days - int(days))
                    for winner_id, user, days in exact_days]

    # Считаем остаток
    distributed = sum(floored for _, _, floored, _ in floored_days)
    remainder = total_days - distributed

    # Сортируем по убыванию дробной части
    floored_days.sort(key=lambda x: x[3], reverse=True)

    # Распределяем остаток
    result = []
    for i, (winner_id, user, floored, _) in enumerate(floored_days):
        days_count = floored + (1 if i < remainder else 0)
        result.append((winner_id, user, days_count))

    # Сортируем обратно по убыванию очков (для красивого вывода)
    result.sort(key=lambda x: next(score for wid, _, score in winners_scores if wid == x[0]), reverse=True)

    return result


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
        # Рассчитываем сумму взвешенных очков победителей для процентов
        total_weighted_score = sum(results[winner_id]['weighted'] for winner_id, _ in winners)

        # Используем пропорциональное распределение для расчета дней
        winners_scores = []
        for winner_id, winner in winners:
            weighted_score = results[winner_id]['weighted']
            winners_scores.append((winner_id, winner, weighted_score))

        # Получаем пропорциональное распределение дней
        proportional_distribution = distribute_days_proportionally(winners_scores, missed_days_count)

        for winner_id, winner, days_count in proportional_distribution:
            # Рассчитываем процент от общих взвешенных очков
            winner_weighted_score = results[winner_id]['weighted']
            if total_weighted_score > 0:
                percentage = (winner_weighted_score / total_weighted_score) * 100
                percentage_str = f"{percentage:.1f}%"
            else:
                percentage_str = "0.0%"

            # Формируем правильное склонение для "день"
            if days_count % 10 == 1 and days_count % 100 != 11:
                days_word = "день"
            elif days_count % 10 in [2, 3, 4] and days_count % 100 not in [12, 13, 14]:
                days_word = "дня"
            else:
                days_word = "дней"

            days_distribution_list.append(
                f"• {escape_markdown2(winner.full_username())} получает *{days_count}* {escape_word(days_word)} \\({escape_markdown2(percentage_str)} от общих очков\\) в свою копилку\\!"
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
