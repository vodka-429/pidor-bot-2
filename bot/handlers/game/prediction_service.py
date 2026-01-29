"""Service functions for predictions (магазин пидор-койнов)."""
import json
import logging
import math
from typing import List, Tuple

from sqlmodel import select

from bot.app.models import Prediction, TGUser
from bot.handlers.game.coin_service import add_coins
from bot.utils import escape_markdown2, format_number

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Награда за правильное предсказание
PREDICTION_REWARD = 30


def calculate_candidates_count(players_count: int) -> int:
    """
    Рассчитать количество кандидатов для предсказания.

    Формула: ceil(количество_игроков / 10)
    Это выравнивает вероятность угадывания примерно до 10-15% для всех размеров чатов.

    Args:
        players_count: Количество игроков в чате

    Returns:
        Количество кандидатов для выбора
    """
    return math.ceil(players_count / 10)


def get_predicted_user_ids(prediction: Prediction) -> List[int]:
    """
    Получить список ID кандидатов из предсказания.

    Args:
        prediction: Объект предсказания

    Returns:
        Список ID предсказанных пользователей
    """
    return json.loads(prediction.predicted_user_ids)


def get_predictions_for_day(db_session, game_id: int, year: int, day: int) -> List[Prediction]:
    """
    Получить все предсказания на день.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        year: Год
        day: День года

    Returns:
        Список предсказаний на указанный день
    """
    stmt = select(Prediction).where(
        Prediction.game_id == game_id,
        Prediction.year == year,
        Prediction.day == day
    )
    predictions = db_session.exec(stmt).all()

    logger.info(f"Found {len(predictions)} predictions for game {game_id}, day {year}-{day}")
    return predictions


def process_predictions(
    db_session,
    game_id: int,
    year: int,
    day: int,
    winner_id: int
) -> List[Tuple[Prediction, bool]]:
    """
    Обработать предсказания и вернуть список с результатами.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        year: Год
        day: День года
        winner_id: ID победителя

    Returns:
        Список кортежей (предсказание, правильность)
    """
    predictions = get_predictions_for_day(db_session, game_id, year, day)
    results = []

    for prediction in predictions:
        # Проверяем, есть ли winner_id среди предсказанных кандидатов
        predicted_ids = get_predicted_user_ids(prediction)
        is_correct = winner_id in predicted_ids
        prediction.is_correct = is_correct

        results.append((prediction, is_correct))

        if is_correct:
            logger.info(f"User {prediction.user_id} correctly predicted winner {winner_id}")
        else:
            logger.info(f"User {prediction.user_id} incorrectly predicted {predicted_ids}, actual winner: {winner_id}")

        db_session.add(prediction)

    return results


def format_predictions_summary(predictions_results: List[Tuple[Prediction, bool]], db_session) -> str:
    """
    Форматировать результаты предсказаний в одно сообщение.

    Args:
        predictions_results: Список кортежей (предсказание, правильность)
        db_session: Сессия базы данных

    Returns:
        Отформатированное сообщение с результатами всех предсказаний
    """
    from bot.handlers.game.text_static import (
        PREDICTIONS_SUMMARY_HEADER,
        PREDICTIONS_SUMMARY_CORRECT_ITEM,
        PREDICTIONS_SUMMARY_INCORRECT_ITEM
    )
    from bot.handlers.game.coin_service import get_balance

    if not predictions_results:
        return ""

    lines = [PREDICTIONS_SUMMARY_HEADER]

    for prediction, is_correct in predictions_results:
        # Получаем пользователя, который сделал предсказание
        stmt = select(TGUser).where(TGUser.id == prediction.user_id)
        predictor = db_session.exec(stmt).one()

        if is_correct:
            # Получаем новый баланс предсказателя
            predictor_balance = get_balance(db_session, prediction.game_id, prediction.user_id)
            line = PREDICTIONS_SUMMARY_CORRECT_ITEM.format(
                username=escape_markdown2(predictor.full_username()),
                balance=format_number(predictor_balance)
            )
        else:
            line = PREDICTIONS_SUMMARY_INCORRECT_ITEM.format(
                username=escape_markdown2(predictor.full_username())
            )

        lines.append(line)

    result = '\n'.join(lines)
    logger.info(f"Formatted predictions summary with {len(predictions_results)} predictions")
    return result


def format_predictions_summary_html(predictions_results: List[Tuple[Prediction, bool]], db_session) -> str:
    """
    Форматировать результаты предсказаний в HTML для объединённого сообщения.

    Args:
        predictions_results: Список кортежей (предсказание, правильность)
        db_session: Сессия базы данных

    Returns:
        Отформатированное HTML-сообщение с результатами всех предсказаний
    """
    from html import escape as html_escape
    from bot.handlers.game.coin_service import get_balance

    if not predictions_results:
        return ""

    lines = ["🔮 <b>Результаты предсказаний:</b>"]

    for prediction, is_correct in predictions_results:
        # Получаем пользователя, который сделал предсказание
        stmt = select(TGUser).where(TGUser.id == prediction.user_id)
        predictor = db_session.exec(stmt).one()

        if is_correct:
            line = f"✅ {html_escape(predictor.full_username())} угадал(а)! +30 🪙"
        else:
            line = f"❌ {html_escape(predictor.full_username())} не угадал(а)"

        lines.append(line)

    result = '\n'.join(lines)
    logger.info(f"Formatted predictions summary (HTML) with {len(predictions_results)} predictions")
    return result


def award_correct_predictions(
    db_session,
    game_id: int,
    year: int,
    predictions_results: List[Tuple[Prediction, bool]]
):
    """
    Начислить койны за правильные предсказания.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        year: Год
        predictions_results: Список кортежей (предсказание, правильность)
    """
    for prediction, is_correct in predictions_results:
        if is_correct:
            # Начисляем койны за правильное предсказание
            add_coins(
                db_session,
                game_id,
                prediction.user_id,
                PREDICTION_REWARD,
                year,
                "prediction_correct",
                auto_commit=False
            )
            logger.info(f"Awarded {PREDICTION_REWARD} coins to user {prediction.user_id} for correct prediction")


def process_predictions_for_reroll(
    db_session,
    game_id: int,
    year: int,
    day: int,
    new_winner_id: int
) -> List[Tuple[Prediction, bool]]:
    """
    Обработать предсказания при перевыборе.

    ВАЖНО: Не отменяет награды за старого победителя!
    Проверяет предсказания по новому победителю и начисляет дополнительные награды.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        year: Год
        day: День года
        new_winner_id: ID нового победителя после перевыбора

    Returns:
        Список кортежей (предсказание, правильность для нового победителя)
    """
    predictions = get_predictions_for_day(db_session, game_id, year, day)
    results = []

    for prediction in predictions:
        # Проверяем, есть ли new_winner_id среди предсказанных кандидатов
        predicted_ids = get_predicted_user_ids(prediction)
        is_correct_for_new_winner = new_winner_id in predicted_ids

        # Если предсказание уже было правильным (для старого победителя),
        # и оно также правильно для нового - это двойная награда
        # Если было неправильным, но стало правильным - начисляем награду
        if is_correct_for_new_winner:
            # Начисляем койны за правильное предсказание при перевыборе
            add_coins(
                db_session,
                game_id,
                prediction.user_id,
                PREDICTION_REWARD,
                year,
                "prediction_correct_reroll",
                auto_commit=False
            )
            logger.info(
                f"User {prediction.user_id} correctly predicted new winner {new_winner_id} "
                f"after reroll (was correct for old: {prediction.is_correct})"
            )
        else:
            logger.info(
                f"User {prediction.user_id} did not predict new winner {new_winner_id} "
                f"(was correct for old: {prediction.is_correct})"
            )

        results.append((prediction, is_correct_for_new_winner))

    return results


def get_or_create_prediction_draft(db_session, game_id: int, user_id: int, candidates_count: int):
    """
    Получить или создать черновик предсказания.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
        candidates_count: Количество кандидатов для выбора

    Returns:
        Объект PredictionDraft
    """
    from bot.app.models import PredictionDraft

    stmt = select(PredictionDraft).where(
        PredictionDraft.game_id == game_id,
        PredictionDraft.user_id == user_id
    )
    draft = db_session.exec(stmt).first()

    if draft is None:
        # Создаём новый черновик с пустым списком выбранных
        draft = PredictionDraft(
            game_id=game_id,
            user_id=user_id,
            selected_user_ids=json.dumps([]),
            candidates_count=candidates_count
        )
        db_session.add(draft)
        db_session.commit()
        db_session.refresh(draft)
        logger.info(f"Created new prediction draft for user {user_id} in game {game_id}")

    return draft


def update_prediction_draft(db_session, draft_id: int, selected_user_ids: List[int]):
    """
    Обновить выбранных кандидатов в черновике.

    Args:
        db_session: Сессия базы данных
        draft_id: ID черновика
        selected_user_ids: Список ID выбранных пользователей
    """
    from bot.app.models import PredictionDraft
    from datetime import datetime

    stmt = select(PredictionDraft).where(PredictionDraft.id == draft_id)
    draft = db_session.exec(stmt).one()

    draft.selected_user_ids = json.dumps(selected_user_ids)
    draft.updated_at = datetime.utcnow()

    db_session.add(draft)
    db_session.commit()

    logger.info(f"Updated prediction draft {draft_id} with {len(selected_user_ids)} selected candidates")


def delete_prediction_draft(db_session, game_id: int, user_id: int):
    """
    Удалить черновик предсказания после подтверждения или отмены.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя
    """
    from bot.app.models import PredictionDraft

    stmt = select(PredictionDraft).where(
        PredictionDraft.game_id == game_id,
        PredictionDraft.user_id == user_id
    )
    draft = db_session.exec(stmt).first()

    if draft:
        db_session.delete(draft)
        db_session.commit()
        logger.info(f"Deleted prediction draft for user {user_id} in game {game_id}")


def get_prediction_draft(db_session, game_id: int, user_id: int):
    """
    Получить текущий черновик предсказания.

    Args:
        db_session: Сессия базы данных
        game_id: ID игры (чата)
        user_id: ID пользователя

    Returns:
        Объект PredictionDraft или None, если черновик не найден
    """
    from bot.app.models import PredictionDraft

    stmt = select(PredictionDraft).where(
        PredictionDraft.game_id == game_id,
        PredictionDraft.user_id == user_id
    )
    draft = db_session.exec(stmt).first()

    if draft:
        logger.info(f"Found prediction draft for user {user_id} in game {game_id}")

    return draft
