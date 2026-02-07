"""Tests for prediction service functionality."""
import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from bot.handlers.game.prediction_service import (
    get_predictions_for_day,
    process_predictions,
    process_predictions_for_reroll,
    format_predictions_summary,
    award_correct_predictions,
    calculate_candidates_count,
    get_predicted_user_ids,
)
from bot.handlers.game.config import get_config
from bot.app.models import Prediction, TGUser

# Получаем значение награды из конфигурации по умолчанию
DEFAULT_PREDICTION_REWARD = get_config(0).constants.prediction_reward


@pytest.mark.unit
def test_get_predictions_for_day_returns_predictions(mock_db_session):
    """Test get_predictions_for_day returns list of predictions."""
    # Setup
    game_id = 1
    year = 2024
    day = 167

    # Create mock predictions with JSON list of candidates
    prediction1 = Prediction(
        id=1,
        game_id=game_id,
        user_id=1,
        predicted_user_ids=json.dumps([2]),
        year=year,
        day=day
    )
    prediction2 = Prediction(
        id=2,
        game_id=game_id,
        user_id=3,
        predicted_user_ids=json.dumps([2]),
        year=year,
        day=day
    )

    # Mock exec to return predictions
    mock_result = MagicMock()
    mock_result.all.return_value = [prediction1, prediction2]
    mock_db_session.exec.return_value = mock_result

    # Execute
    predictions = get_predictions_for_day(mock_db_session, game_id, year, day)

    # Verify
    assert len(predictions) == 2
    assert predictions[0] == prediction1
    assert predictions[1] == prediction2


@pytest.mark.unit
def test_get_predictions_for_day_empty(mock_db_session):
    """Test get_predictions_for_day returns empty list when no predictions."""
    # Setup
    game_id = 1
    year = 2024
    day = 167

    # Mock exec to return empty list
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Execute
    predictions = get_predictions_for_day(mock_db_session, game_id, year, day)

    # Verify
    assert len(predictions) == 0


@pytest.mark.unit
def test_process_predictions_correct(mock_db_session):
    """Test process_predictions marks correct prediction."""
    # Setup
    game_id = 1
    year = 2024
    day = 167
    winner_id = 2

    # Create mock prediction with JSON list of candidates
    prediction = Prediction(
        id=1,
        game_id=game_id,
        user_id=1,
        predicted_user_ids=json.dumps([2]),  # Matches winner_id
        year=year,
        day=day
    )

    # Mock exec to return prediction
    mock_result = MagicMock()
    mock_result.all.return_value = [prediction]
    mock_db_session.exec.return_value = mock_result

    # Execute
    results = process_predictions(mock_db_session, game_id, year, day, winner_id)

    # Verify
    assert len(results) == 1
    pred, is_correct = results[0]
    assert pred == prediction
    assert is_correct is True
    assert prediction.is_correct is True
    mock_db_session.add.assert_called_once_with(prediction)


@pytest.mark.unit
def test_process_predictions_incorrect(mock_db_session):
    """Test process_predictions marks incorrect prediction."""
    # Setup
    game_id = 1
    year = 2024
    day = 167
    winner_id = 3

    # Create mock prediction with JSON list of candidates
    prediction = Prediction(
        id=1,
        game_id=game_id,
        user_id=1,
        predicted_user_ids=json.dumps([2]),  # Does not match winner_id
        year=year,
        day=day
    )

    # Mock exec to return prediction
    mock_result = MagicMock()
    mock_result.all.return_value = [prediction]
    mock_db_session.exec.return_value = mock_result

    # Execute
    results = process_predictions(mock_db_session, game_id, year, day, winner_id)

    # Verify
    assert len(results) == 1
    pred, is_correct = results[0]
    assert pred == prediction
    assert is_correct is False
    assert prediction.is_correct is False


@pytest.mark.unit
def test_process_predictions_multiple(mock_db_session):
    """Test process_predictions handles multiple predictions."""
    # Setup
    game_id = 1
    year = 2024
    day = 167
    winner_id = 2

    # Create mock predictions - one correct, one incorrect
    prediction1 = Prediction(
        id=1,
        game_id=game_id,
        user_id=1,
        predicted_user_ids=json.dumps([2]),  # Correct
        year=year,
        day=day
    )
    prediction2 = Prediction(
        id=2,
        game_id=game_id,
        user_id=3,
        predicted_user_ids=json.dumps([4]),  # Incorrect
        year=year,
        day=day
    )

    # Mock exec to return predictions
    mock_result = MagicMock()
    mock_result.all.return_value = [prediction1, prediction2]
    mock_db_session.exec.return_value = mock_result

    # Execute
    results = process_predictions(mock_db_session, game_id, year, day, winner_id)

    # Verify
    assert len(results) == 2

    pred1, is_correct1 = results[0]
    assert pred1 == prediction1
    assert is_correct1 is True

    pred2, is_correct2 = results[1]
    assert pred2 == prediction2
    assert is_correct2 is False


@pytest.mark.unit
@patch('bot.handlers.game.text_static.PREDICTIONS_SUMMARY_HEADER', '🔮 Результаты предсказаний:')
@patch('bot.handlers.game.text_static.PREDICTIONS_SUMMARY_CORRECT_ITEM', '{username} угадал(а)! Баланс: {balance} 🪙')
@patch('bot.handlers.game.text_static.PREDICTIONS_SUMMARY_INCORRECT_ITEM', '{username} не угадал(а)')
def test_format_predictions_summary_single(mock_db_session):
    """Test format_predictions_summary formats single prediction."""
    # Setup
    game_id = 1
    predictor = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")

    prediction = Prediction(
        id=1,
        game_id=game_id,
        user_id=1,
        predicted_user_ids=json.dumps([2]),
        year=2024,
        day=167,
        is_correct=True
    )

    predictions_results = [(prediction, True)]

    # Mock exec to return predictor for TGUser query and balance for get_balance
    exec_call_count = [0]
    def exec_side_effect(stmt):
        exec_call_count[0] += 1
        mock_result = MagicMock()
        if exec_call_count[0] == 1:
            # First call - TGUser query
            mock_result.one.return_value = predictor
        else:
            # Second call - get_balance query
            mock_result.first.return_value = 50
        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    result = format_predictions_summary(predictions_results, mock_db_session)

    # Verify
    assert '🔮 Результаты предсказаний:' in result
    assert 'player1' in result
    assert '50' in result


@pytest.mark.unit
@patch('bot.handlers.game.text_static.PREDICTIONS_SUMMARY_HEADER', '🔮 Результаты предсказаний:')
@patch('bot.handlers.game.text_static.PREDICTIONS_SUMMARY_CORRECT_ITEM', '{username} угадал(а)! Баланс: {balance} 🪙')
@patch('bot.handlers.game.text_static.PREDICTIONS_SUMMARY_INCORRECT_ITEM', '{username} не угадал(а)')
def test_format_predictions_summary_multiple(mock_db_session):
    """Test format_predictions_summary formats multiple predictions."""
    # Setup
    game_id = 1
    predictor1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    predictor2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")

    prediction1 = Prediction(id=1, game_id=game_id, user_id=1, predicted_user_ids=json.dumps([3]), year=2024, day=167, is_correct=True)
    prediction2 = Prediction(id=2, game_id=game_id, user_id=2, predicted_user_ids=json.dumps([3]), year=2024, day=167, is_correct=True)

    predictions_results = [(prediction1, True), (prediction2, True)]

    # Mock exec to return predictors for TGUser queries and balance for get_balance
    exec_call_count = [0]
    def exec_side_effect(stmt):
        exec_call_count[0] += 1
        mock_result = MagicMock()
        if exec_call_count[0] == 1:
            # First call - TGUser query for predictor1
            mock_result.one.return_value = predictor1
        elif exec_call_count[0] == 2:
            # Second call - get_balance for predictor1
            mock_result.first.return_value = 50
        elif exec_call_count[0] == 3:
            # Third call - TGUser query for predictor2
            mock_result.one.return_value = predictor2
        else:
            # Fourth call - get_balance for predictor2
            mock_result.first.return_value = 50
        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    result = format_predictions_summary(predictions_results, mock_db_session)

    # Verify
    assert '🔮 Результаты предсказаний:' in result
    assert 'player1' in result
    assert 'player2' in result


@pytest.mark.unit
@patch('bot.handlers.game.text_static.PREDICTIONS_SUMMARY_HEADER', '🔮 Результаты предсказаний:')
@patch('bot.handlers.game.text_static.PREDICTIONS_SUMMARY_CORRECT_ITEM', '{username} угадал(а)! Баланс: {balance} 🪙')
@patch('bot.handlers.game.text_static.PREDICTIONS_SUMMARY_INCORRECT_ITEM', '{username} не угадал(а)')
def test_format_predictions_summary_mixed(mock_db_session):
    """Test format_predictions_summary formats mixed correct/incorrect predictions."""
    # Setup
    game_id = 1
    predictor1 = TGUser(id=1, tg_id=101, first_name="Player1", username="player1")
    predictor2 = TGUser(id=2, tg_id=102, first_name="Player2", username="player2")

    prediction1 = Prediction(id=1, game_id=game_id, user_id=1, predicted_user_ids=json.dumps([3]), year=2024, day=167, is_correct=True)
    prediction2 = Prediction(id=2, game_id=game_id, user_id=2, predicted_user_ids=json.dumps([4]), year=2024, day=167, is_correct=False)

    predictions_results = [(prediction1, True), (prediction2, False)]

    # Mock exec to return predictors for TGUser queries and balance for get_balance
    exec_call_count = [0]
    def exec_side_effect(stmt):
        exec_call_count[0] += 1
        mock_result = MagicMock()
        if exec_call_count[0] == 1:
            # First call - TGUser query for predictor1
            mock_result.one.return_value = predictor1
        elif exec_call_count[0] == 2:
            # Second call - get_balance for predictor1
            mock_result.first.return_value = 50
        elif exec_call_count[0] == 3:
            # Third call - TGUser query for predictor2
            mock_result.one.return_value = predictor2
        else:
            # Note: predictor2 is incorrect, so no get_balance call
            mock_result.first.return_value = 50
        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    result = format_predictions_summary(predictions_results, mock_db_session)

    # Verify
    assert '🔮 Результаты предсказаний:' in result
    assert 'player1' in result
    assert 'player2' in result
    assert 'угадал(а)' in result
    assert 'не угадал(а)' in result


@pytest.mark.unit
@patch('bot.handlers.game.prediction_service.add_coins')
def test_award_correct_predictions(mock_add_coins, mock_db_session):
    """Test award_correct_predictions awards coins for correct predictions."""
    # Setup
    game_id = 1
    year = 2024

    prediction1 = Prediction(id=1, game_id=game_id, user_id=1, predicted_user_ids=json.dumps([2]), year=year, day=167, is_correct=True)
    prediction2 = Prediction(id=2, game_id=game_id, user_id=3, predicted_user_ids=json.dumps([4]), year=year, day=167, is_correct=False)
    prediction3 = Prediction(id=3, game_id=game_id, user_id=5, predicted_user_ids=json.dumps([2]), year=year, day=167, is_correct=True)

    predictions_results = [(prediction1, True), (prediction2, False), (prediction3, True)]

    # Execute
    award_correct_predictions(mock_db_session, game_id, year, predictions_results)

    # Verify - should award coins only for correct predictions
    assert mock_add_coins.call_count == 2

    # Check first correct prediction
    call_args_1 = mock_add_coins.call_args_list[0]
    assert call_args_1[0][0] == mock_db_session
    assert call_args_1[0][1] == game_id
    assert call_args_1[0][2] == 1  # user_id
    assert call_args_1[0][3] == DEFAULT_PREDICTION_REWARD
    assert call_args_1[0][4] == year
    assert call_args_1[0][5] == "prediction_correct"
    assert call_args_1[1]['auto_commit'] is False

    # Check second correct prediction
    call_args_2 = mock_add_coins.call_args_list[1]
    assert call_args_2[0][2] == 5  # user_id


@pytest.mark.unit
@patch('bot.handlers.game.prediction_service.add_coins')
def test_process_predictions_for_reroll_correct_in_main_incorrect_in_reroll(mock_add_coins, mock_db_session):
    """
    Тест: предсказание сбылось в основном розыгрыше, не сбылось при перевыборе.
    Награда за основной розыгрыш сохраняется, дополнительная награда не начисляется.
    """
    # Setup
    game_id = 1
    year = 2024
    day = 167
    old_winner_id = 2
    new_winner_id = 3

    # Предсказание было правильным для старого победителя
    prediction = Prediction(
        id=1,
        game_id=game_id,
        user_id=1,
        predicted_user_ids=json.dumps([2]),  # Угадал старого победителя
        year=year,
        day=day,
        is_correct=True  # Уже отмечено как правильное
    )

    # Mock exec to return prediction
    mock_result = MagicMock()
    mock_result.all.return_value = [prediction]
    mock_db_session.exec.return_value = mock_result

    # Execute
    results = process_predictions_for_reroll(mock_db_session, game_id, year, day, new_winner_id)

    # Verify
    assert len(results) == 1
    pred, is_correct_for_new = results[0]
    assert pred == prediction
    assert is_correct_for_new is False  # Не угадал нового победителя
    assert prediction.is_correct is True  # Старое значение сохранилось

    # Не должно быть начислений за перевыбор
    mock_add_coins.assert_not_called()


@pytest.mark.unit
@patch('bot.handlers.game.prediction_service.add_coins')
def test_process_predictions_for_reroll_incorrect_in_main_correct_in_reroll(mock_add_coins, mock_db_session):
    """
    Тест: предсказание не сбылось в основном розыгрыше, сбылось при перевыборе.
    Награда начисляется за перевыбор.
    """
    # Setup
    game_id = 1
    year = 2024
    day = 167
    old_winner_id = 2
    new_winner_id = 3

    # Предсказание было неправильным для старого победителя
    prediction = Prediction(
        id=1,
        game_id=game_id,
        user_id=1,
        predicted_user_ids=json.dumps([3, 4]),  # Не угадал старого, но есть новый
        year=year,
        day=day,
        is_correct=False  # Было неправильным
    )

    # Mock exec to return prediction
    mock_result = MagicMock()
    mock_result.all.return_value = [prediction]
    mock_db_session.exec.return_value = mock_result

    # Execute
    results = process_predictions_for_reroll(mock_db_session, game_id, year, day, new_winner_id)

    # Verify
    assert len(results) == 1
    pred, is_correct_for_new = results[0]
    assert pred == prediction
    assert is_correct_for_new is True  # Угадал нового победителя
    assert prediction.is_correct is False  # Старое значение сохранилось

    # Должна быть одна награда за перевыбор
    mock_add_coins.assert_called_once()
    call_args = mock_add_coins.call_args
    assert call_args[0][0] == mock_db_session
    assert call_args[0][1] == game_id
    assert call_args[0][2] == 1  # user_id
    assert call_args[0][3] == DEFAULT_PREDICTION_REWARD
    assert call_args[0][4] == year
    assert call_args[0][5] == "prediction_correct_reroll"
    assert call_args[1]['auto_commit'] is False


@pytest.mark.unit
@patch('bot.handlers.game.prediction_service.add_coins')
def test_process_predictions_for_reroll_correct_in_both(mock_add_coins, mock_db_session):
    """
    Тест: предсказание сбылось в обоих случаях - двойная награда.
    Игрок угадал и старого, и нового победителя.
    """
    # Setup
    game_id = 1
    year = 2024
    day = 167
    old_winner_id = 2
    new_winner_id = 3

    # Предсказание правильное для обоих победителей
    prediction = Prediction(
        id=1,
        game_id=game_id,
        user_id=1,
        predicted_user_ids=json.dumps([2, 3]),  # Угадал обоих!
        year=year,
        day=day,
        is_correct=True  # Уже получил награду за старого
    )

    # Mock exec to return prediction
    mock_result = MagicMock()
    mock_result.all.return_value = [prediction]
    mock_db_session.exec.return_value = mock_result

    # Execute
    results = process_predictions_for_reroll(mock_db_session, game_id, year, day, new_winner_id)

    # Verify
    assert len(results) == 1
    pred, is_correct_for_new = results[0]
    assert pred == prediction
    assert is_correct_for_new is True  # Угадал нового победителя
    assert prediction.is_correct is True  # Старое значение сохранилось

    # Должна быть дополнительная награда за перевыбор
    mock_add_coins.assert_called_once()
    call_args = mock_add_coins.call_args
    assert call_args[0][0] == mock_db_session
    assert call_args[0][1] == game_id
    assert call_args[0][2] == 1  # user_id
    assert call_args[0][3] == DEFAULT_PREDICTION_REWARD
    assert call_args[0][4] == year
    assert call_args[0][5] == "prediction_correct_reroll"
    assert call_args[1]['auto_commit'] is False


@pytest.mark.unit
@patch('bot.handlers.game.prediction_service.add_coins')
def test_process_predictions_for_reroll_multiple_predictions(mock_add_coins, mock_db_session):
    """
    Тест: несколько предсказаний при перевыборе с разными результатами.
    """
    # Setup
    game_id = 1
    year = 2024
    day = 167
    new_winner_id = 3

    # Три предсказания с разными результатами
    prediction1 = Prediction(
        id=1,
        game_id=game_id,
        user_id=1,
        predicted_user_ids=json.dumps([2, 3]),  # Угадал обоих
        year=year,
        day=day,
        is_correct=True
    )
    prediction2 = Prediction(
        id=2,
        game_id=game_id,
        user_id=2,
        predicted_user_ids=json.dumps([3, 4]),  # Не угадал старого, угадал нового
        year=year,
        day=day,
        is_correct=False
    )
    prediction3 = Prediction(
        id=3,
        game_id=game_id,
        user_id=3,
        predicted_user_ids=json.dumps([2, 5]),  # Угадал старого, не угадал нового
        year=year,
        day=day,
        is_correct=True
    )

    # Mock exec to return predictions
    mock_result = MagicMock()
    mock_result.all.return_value = [prediction1, prediction2, prediction3]
    mock_db_session.exec.return_value = mock_result

    # Execute
    results = process_predictions_for_reroll(mock_db_session, game_id, year, day, new_winner_id)

    # Verify
    assert len(results) == 3

    # Первое предсказание - угадал обоих
    pred1, is_correct1 = results[0]
    assert pred1 == prediction1
    assert is_correct1 is True

    # Второе предсказание - угадал только нового
    pred2, is_correct2 = results[1]
    assert pred2 == prediction2
    assert is_correct2 is True

    # Третье предсказание - угадал только старого
    pred3, is_correct3 = results[2]
    assert pred3 == prediction3
    assert is_correct3 is False

    # Должно быть 2 награды (для prediction1 и prediction2)
    assert mock_add_coins.call_count == 2

    # Проверяем первую награду (prediction1)
    call_args_1 = mock_add_coins.call_args_list[0]
    assert call_args_1[0][2] == 1  # user_id

    # Проверяем вторую награду (prediction2)
    call_args_2 = mock_add_coins.call_args_list[1]
    assert call_args_2[0][2] == 2  # user_id


@pytest.mark.unit
@patch('bot.handlers.game.prediction_service.add_coins')
def test_process_predictions_for_reroll_no_predictions(mock_add_coins, mock_db_session):
    """
    Тест: нет предсказаний для обработки при перевыборе.
    """
    # Setup
    game_id = 1
    year = 2024
    day = 167
    new_winner_id = 3

    # Mock exec to return empty list
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_db_session.exec.return_value = mock_result

    # Execute
    results = process_predictions_for_reroll(mock_db_session, game_id, year, day, new_winner_id)

    # Verify
    assert len(results) == 0
    mock_add_coins.assert_not_called()
