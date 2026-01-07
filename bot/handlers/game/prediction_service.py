"""Service functions for predictions (магазин пидор-койнов)."""
import logging
from typing import List, Tuple

from sqlmodel import select

from bot.app.models import Prediction, TGUser
from bot.handlers.game.coin_service import add_coins
from bot.utils import escape_markdown2, format_number

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

# Награда за правильное предсказание
PREDICTION_REWARD = 30


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
        # Проверяем, совпал ли predicted_user_id с winner_id
        is_correct = prediction.predicted_user_id == winner_id
        prediction.is_correct = is_correct

        results.append((prediction, is_correct))

        if is_correct:
            logger.info(f"User {prediction.user_id} correctly predicted winner {winner_id}")
        else:
            logger.info(f"User {prediction.user_id} incorrectly predicted {prediction.predicted_user_id}, actual winner: {winner_id}")

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
