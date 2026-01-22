"""Tests for shop service functionality."""
import pytest
from unittest.mock import MagicMock, Mock
from datetime import date, timedelta

from bot.handlers.game.shop_service import (
    get_or_create_player_effects,
    spend_coins,
    can_afford,
    get_shop_items,
    buy_immunity,
    buy_double_chance,
    create_prediction,
    IMMUNITY_PRICE,
    DOUBLE_CHANCE_PRICE,
    PREDICTION_PRICE,
    IMMUNITY_COOLDOWN_DAYS
)
from bot.app.models import GamePlayerEffect, Prediction, PidorCoinTransaction


@pytest.mark.unit
def test_get_or_create_player_effects_creates_new(mock_db_session):
    """Test get_or_create_player_effects creates new record when none exists."""
    # Setup
    game_id = 1
    user_id = 1

    # Mock exec returning None (no existing record)
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_or_create_player_effects(mock_db_session, game_id, user_id)

    # Verify new record was created
    mock_db_session.add.assert_called_once()
    added_effect = mock_db_session.add.call_args[0][0]

    assert isinstance(added_effect, GamePlayerEffect)
    assert added_effect.game_id == game_id
    assert added_effect.user_id == user_id
    assert added_effect.next_win_multiplier == 1

    # Verify commit and refresh were called
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()


@pytest.mark.unit
def test_get_or_create_player_effects_returns_existing(mock_db_session):
    """Test get_or_create_player_effects returns existing record."""
    # Setup
    game_id = 1
    user_id = 1

    existing_effect = GamePlayerEffect(
        game_id=game_id,
        user_id=user_id,
        next_win_multiplier=1
    )

    # Mock exec returning existing record
    mock_result = MagicMock()
    mock_result.first.return_value = existing_effect
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = get_or_create_player_effects(mock_db_session, game_id, user_id)

    # Verify existing record was returned without creating new one
    assert result == existing_effect
    mock_db_session.add.assert_not_called()
    mock_db_session.commit.assert_not_called()


@pytest.mark.unit
def test_spend_coins_success(mock_db_session):
    """Test spend_coins creates negative transaction."""
    # Setup
    game_id = 1
    user_id = 1
    amount = 10
    year = 2024
    reason = "shop_immunity"

    # Execute
    result = spend_coins(mock_db_session, game_id, user_id, amount, year, reason)

    # Verify transaction was created
    mock_db_session.add.assert_called_once()
    added_transaction = mock_db_session.add.call_args[0][0]

    assert isinstance(added_transaction, PidorCoinTransaction)
    assert added_transaction.game_id == game_id
    assert added_transaction.user_id == user_id
    assert added_transaction.amount == -amount  # Negative for spending
    assert added_transaction.year == year
    assert added_transaction.reason == reason

    # Verify commit and refresh were called
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()


@pytest.mark.unit
def test_spend_coins_creates_negative_transaction(mock_db_session):
    """Test spend_coins creates transaction with negative amount."""
    # Setup
    game_id = 1
    user_id = 1
    amount = 5
    year = 2024
    reason = "shop_double_chance"

    # Execute
    result = spend_coins(mock_db_session, game_id, user_id, amount, year, reason)

    # Verify negative amount
    added_transaction = mock_db_session.add.call_args[0][0]
    assert added_transaction.amount == -5


@pytest.mark.unit
def test_spend_coins_raises_error_for_negative_amount(mock_db_session):
    """Test spend_coins raises ValueError for negative amount."""
    # Setup
    game_id = 1
    user_id = 1
    amount = -10  # Negative amount should raise error
    year = 2024
    reason = "test"

    # Execute and verify
    with pytest.raises(ValueError, match="Amount must be positive"):
        spend_coins(mock_db_session, game_id, user_id, amount, year, reason)

    # Verify no transaction was created
    mock_db_session.add.assert_not_called()


@pytest.mark.unit
def test_can_afford_true(mock_db_session):
    """Test can_afford returns True when user has enough coins."""
    # Setup
    game_id = 1
    user_id = 1
    price = 10
    balance = 15

    # Mock get_balance to return sufficient balance
    mock_result = MagicMock()
    mock_result.first.return_value = balance
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = can_afford(mock_db_session, game_id, user_id, price)

    # Verify
    assert result is True


@pytest.mark.unit
def test_can_afford_false(mock_db_session):
    """Test can_afford returns False when user doesn't have enough coins."""
    # Setup
    game_id = 1
    user_id = 1
    price = 10
    balance = 5

    # Mock get_balance to return insufficient balance
    mock_result = MagicMock()
    mock_result.first.return_value = balance
    mock_db_session.exec.return_value = mock_result

    # Execute
    result = can_afford(mock_db_session, game_id, user_id, price)

    # Verify
    assert result is False


@pytest.mark.unit
def test_get_shop_items():
    """Test get_shop_items returns list of available items."""
    # Execute
    items = get_shop_items()

    # Verify - now includes transfer and bank
    assert len(items) == 5
    assert items[0]['name'] == '🛡️ Защита от пидора'
    assert items[0]['price'] == IMMUNITY_PRICE
    assert items[0]['callback_data'] == 'shop_immunity'

    assert items[1]['name'] == '🎲 Двойной шанс'
    assert items[1]['price'] == DOUBLE_CHANCE_PRICE
    assert items[1]['callback_data'] == 'shop_double'

    assert items[2]['name'] == '🔮 Предсказание'
    assert items[2]['price'] == PREDICTION_PRICE
    assert items[2]['callback_data'] == 'shop_predict'

    # New items
    assert items[3]['name'] == '💸 Передать койны'
    assert items[3]['callback_data'] == 'shop_transfer'

    assert items[4]['name'] == '🏦 Банк чата'
    assert items[4]['callback_data'] == 'shop_bank'


@pytest.mark.unit
def test_buy_immunity_success(mock_db_session):
    """Test buy_immunity successfully purchases immunity."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024
    current_date = date(2024, 6, 15)  # Day 167 of 2024

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 20

    # Mock no existing effect
    mock_effect = GamePlayerEffect(
        game_id=game_id,
        user_id=user_id,
        immunity_year=None,
        immunity_day=None
    )
    mock_effect_result = MagicMock()
    mock_effect_result.first.return_value = mock_effect

    # Configure exec to return different results
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # First call for balance
            return mock_balance_result
        else:  # Second call for effect
            return mock_effect_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = buy_immunity(mock_db_session, game_id, user_id, year, current_date)

    # Verify
    assert success is True
    assert message == "success"

    # Verify immunity is set for tomorrow (June 16, day 168)
    assert mock_effect.immunity_year == 2024
    assert mock_effect.immunity_day == 168  # June 16 is day 168 (June 15 is day 167)

    # Verify commit was called
    mock_db_session.commit.assert_called()


@pytest.mark.unit
def test_buy_immunity_insufficient_funds(mock_db_session):
    """Test buy_immunity fails when user doesn't have enough coins."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024
    current_date = date(2024, 6, 15)

    # Mock insufficient balance
    mock_result = MagicMock()
    mock_result.first.return_value = 5  # Less than IMMUNITY_PRICE
    mock_db_session.exec.return_value = mock_result

    # Execute
    success, message = buy_immunity(mock_db_session, game_id, user_id, year, current_date)

    # Verify
    assert success is False
    assert message == "insufficient_funds"


@pytest.mark.unit
def test_buy_immunity_already_active(mock_db_session):
    """Test buy_immunity fails when immunity is already active."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024
    current_date = date(2024, 6, 15)  # Day 167

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 20

    # Mock existing effect with active immunity for tomorrow (June 16 = day 168)
    existing_effect = GamePlayerEffect(
        game_id=game_id,
        user_id=user_id,
        immunity_year=2024,
        immunity_day=168,  # Tomorrow (June 16)
        next_win_multiplier=1
    )
    mock_effect_result = MagicMock()
    mock_effect_result.first.return_value = existing_effect

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Effect check
            return mock_effect_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = buy_immunity(mock_db_session, game_id, user_id, year, current_date)

    # Verify
    assert success is False
    assert message.startswith("already_active:")
    assert "2024:168" in message


@pytest.mark.unit
def test_buy_immunity_cooldown(mock_db_session):
    """Test buy_immunity fails when immunity is on cooldown."""
    # Setup
    game_id = 1
    user_id = 1
    year = 2024
    current_date = date(2024, 6, 15)

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 20

    # Mock existing effect with recent immunity_last_used (within cooldown)
    existing_effect = GamePlayerEffect(
        game_id=game_id,
        user_id=user_id,
        immunity_year=None,
        immunity_day=None,
        immunity_last_used=date(2024, 6, 10),  # 5 days ago (cooldown is 7 days)
        next_win_multiplier=1
    )
    mock_effect_result = MagicMock()
    mock_effect_result.first.return_value = existing_effect

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Effect check
            return mock_effect_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = buy_immunity(mock_db_session, game_id, user_id, year, current_date)

    # Verify
    assert success is False
    assert message.startswith("cooldown:")
    expected_cooldown_end = date(2024, 6, 17)  # 10 + 7 days
    assert message == f"cooldown:{expected_cooldown_end.isoformat()}"


@pytest.mark.unit
def test_buy_double_chance_for_self(mock_db_session):
    """Test buy_double_chance successfully purchases double chance for self."""
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    user_id = 1
    target_user_id = 1  # Покупка для себя
    year = 2024
    current_date = date(2024, 6, 15)

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 10

    # Mock no existing purchase
    mock_purchase_result = MagicMock()
    mock_purchase_result.first.return_value = None

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Purchase check
            return mock_purchase_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = buy_double_chance(mock_db_session, game_id, user_id, target_user_id, year, current_date)

    # Verify
    assert success is True
    assert message == "success"

    # Verify DoubleChancePurchase was added
    assert mock_db_session.add.call_count >= 2  # Transaction + DoubleChancePurchase

    # Verify commit was called
    mock_db_session.commit.assert_called()


@pytest.mark.unit
def test_buy_double_chance_for_other(mock_db_session):
    """Test buy_double_chance successfully purchases double chance for another player."""
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    user_id = 1  # Покупатель
    target_user_id = 2  # Целевой игрок
    year = 2024
    current_date = date(2024, 6, 15)

    # Mock sufficient balance for buyer
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 10

    # Mock no existing purchase
    mock_purchase_result = MagicMock()
    mock_purchase_result.first.return_value = None

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Purchase check
            return mock_purchase_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = buy_double_chance(mock_db_session, game_id, user_id, target_user_id, year, current_date)

    # Verify
    assert success is True
    assert message == "success"

    # Verify commit was called
    mock_db_session.commit.assert_called()


@pytest.mark.unit
def test_buy_double_chance_tracks_buyer(mock_db_session):
    """Test buy_double_chance tracks who bought the double chance."""
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    user_id = 1  # Покупатель
    target_user_id = 2  # Целевой игрок
    year = 2024
    current_date = date(2024, 6, 15)

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 10

    # Mock no existing purchase
    mock_purchase_result = MagicMock()
    mock_purchase_result.first.return_value = None

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Purchase check
            return mock_purchase_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = buy_double_chance(mock_db_session, game_id, user_id, target_user_id, year, current_date)

    # Verify
    assert success is True

    # Verify that DoubleChancePurchase was created with correct buyer_id and target_id
    added_objects = [call[0][0] for call in mock_db_session.add.call_args_list]
    purchase = next((obj for obj in added_objects if isinstance(obj, DoubleChancePurchase)), None)
    assert purchase is not None, "DoubleChancePurchase should be created"
    assert purchase.buyer_id == user_id
    assert purchase.target_id == target_user_id


@pytest.mark.unit
def test_create_prediction_success(mock_db_session):
    """Test create_prediction successfully creates prediction."""
    # Setup
    game_id = 1
    user_id = 1
    predicted_user_ids = [2, 3]  # Now it's a list
    year = 2024
    day = 167

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 20

    # Mock no existing prediction
    mock_prediction_result = MagicMock()
    mock_prediction_result.first.return_value = None

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Prediction check
            return mock_prediction_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = create_prediction(mock_db_session, game_id, user_id, predicted_user_ids, year, day)

    # Verify
    assert success is True
    assert message == "success"

    # Verify prediction was added
    assert mock_db_session.add.call_count == 2  # Transaction + prediction
    mock_db_session.commit.assert_called()


@pytest.mark.unit
def test_create_prediction_already_exists(mock_db_session):
    """Test create_prediction fails when prediction already exists for the day."""
    # Setup
    game_id = 1
    user_id = 1
    predicted_user_ids = [2, 3]  # Now it's a list
    year = 2024
    day = 167

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 20

    # Mock existing prediction
    existing_prediction = Prediction(
        game_id=game_id,
        user_id=user_id,
        predicted_user_ids='[2, 3]',  # JSON string
        year=year,
        day=day
    )
    mock_prediction_result = MagicMock()
    mock_prediction_result.first.return_value = existing_prediction

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Prediction check
            return mock_prediction_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = create_prediction(mock_db_session, game_id, user_id, predicted_user_ids, year, day)

    # Verify
    assert success is False
    assert message == "already_exists"


@pytest.mark.unit
def test_create_prediction_self(mock_db_session):
    """Test create_prediction allows user to predict themselves."""
    # Setup
    game_id = 1
    user_id = 1
    predicted_user_ids = [1, 2]  # Includes self
    year = 2024
    day = 167

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 20

    # Mock no existing prediction
    mock_prediction_result = MagicMock()
    mock_prediction_result.first.return_value = None

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Prediction check
            return mock_prediction_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = create_prediction(mock_db_session, game_id, user_id, predicted_user_ids, year, day)

    # Verify - self-prediction is now allowed
    assert success is True
    assert message == "success"

    # Verify prediction was added
    assert mock_db_session.add.call_count == 2  # Transaction + prediction
    mock_db_session.commit.assert_called()


@pytest.mark.unit
def test_effects_isolated_by_game(mock_db_session):
    """Test that effects are isolated by game (critical test for multi-game support)."""
    # Setup


@pytest.mark.unit
def test_buy_immunity_year_day_logic(mock_db_session):
    """Test buy_immunity correctly calculates year+day for tomorrow."""
    # Setup - last day of year
    game_id = 1
    user_id = 1
    year = 2024
    current_date = date(2024, 12, 31)  # Последний день года

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 20

    # Mock no existing effect
    mock_effect = GamePlayerEffect(
        game_id=game_id,
        user_id=user_id,
        immunity_year=None,
        immunity_day=None
    )
    mock_effect_result = MagicMock()
    mock_effect_result.first.return_value = mock_effect

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Effect check
            return mock_effect_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = buy_immunity(mock_db_session, game_id, user_id, year, current_date)

    # Verify
    assert success is True
    # Проверяем, что защита установлена на 1 января следующего года
    assert mock_effect.immunity_year == 2025
    assert mock_effect.immunity_day == 1


@pytest.mark.unit
def test_buy_double_chance_already_bought_today(mock_db_session):
    """Test buy_double_chance fails when buyer already bought today."""
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    user_id = 1
    target_user_id = 2
    year = 2024
    current_date = date(2024, 6, 15)

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 10

    # Mock existing purchase for tomorrow
    existing_purchase = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=user_id,
        target_id=target_user_id,
        year=2024,
        day=167,  # Tomorrow (June 16)
        is_used=False
    )
    mock_purchase_result = MagicMock()
    mock_purchase_result.first.return_value = existing_purchase

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Purchase check
            return mock_purchase_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute
    success, message = buy_double_chance(mock_db_session, game_id, user_id, target_user_id, year, current_date)

    # Verify
    assert success is False
    assert message == "already_bought_today"


@pytest.mark.unit
def test_buy_double_chance_multiple_buyers_same_target(mock_db_session):
    """Test multiple buyers can buy double chance for same target."""
    from bot.app.models import DoubleChancePurchase

    # Setup
    game_id = 1
    buyer1_id = 1
    buyer2_id = 2
    target_user_id = 3
    year = 2024
    current_date = date(2024, 6, 15)

    # Mock sufficient balance
    mock_balance_result = MagicMock()
    mock_balance_result.first.return_value = 10

    # Mock no existing purchase for buyer2
    mock_purchase_result = MagicMock()
    mock_purchase_result.first.return_value = None

    # Configure exec
    call_count = 0
    def exec_side_effect(stmt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Balance check
            return mock_balance_result
        else:  # Purchase check
            return mock_purchase_result

    mock_db_session.exec.side_effect = exec_side_effect

    # Execute - buyer2 buys for same target
    success, message = buy_double_chance(mock_db_session, game_id, buyer2_id, target_user_id, year, current_date)

    # Verify
    assert success is True
    assert message == "success"


@pytest.mark.unit
def test_get_active_effects(mock_db_session):
    """Test get_active_effects returns correct status."""
    from bot.handlers.game.shop_service import get_active_effects, get_or_create_player_effects
    from bot.app.models import DoubleChancePurchase, Prediction

    # Setup
    game_id = 1
    user_id = 1
    current_date = date(2024, 6, 15)  # Day 167

    # Mock effect with immunity for tomorrow (day 168)
    effect = GamePlayerEffect(
        game_id=game_id,
        user_id=user_id,
        immunity_year=2024,
        immunity_day=168,  # Tomorrow
        next_win_multiplier=1
    )

    # Mock double chance purchase for tomorrow
    purchase = DoubleChancePurchase(
        game_id=game_id,
        buyer_id=user_id,
        target_id=user_id,
        year=2024,
        day=168,  # Tomorrow
        is_used=False
    )

    # Mock prediction for tomorrow
    prediction = Prediction(
        game_id=game_id,
        user_id=user_id,
        predicted_user_id=2,
        year=2024,
        day=168  # Tomorrow
    )

    # Patch get_or_create_player_effects
    import bot.handlers.game.shop_service as shop_service
    original_get_effects = shop_service.get_or_create_player_effects
    shop_service.get_or_create_player_effects = lambda db, gid, uid: effect

    # Configure exec to return purchases and predictions
    def exec_side_effect(stmt):
        stmt_str = str(stmt).lower()
        mock_result = MagicMock()
        if 'doublechancepurchase' in stmt_str:
            mock_result.first.return_value = purchase
        elif 'prediction' in stmt_str:
            mock_result.first.return_value = prediction
        else:
            mock_result.first.return_value = None
        return mock_result

    mock_db_session.exec.side_effect = exec_side_effect

    try:
        # Execute
        result = get_active_effects(mock_db_session, game_id, user_id, current_date)

        # Verify
        assert result['immunity_active'] is True
        # format_date_readable returns "16 июня 2024" because 2024 != current year (2026)
        assert result['immunity_date'] == "16 июня 2024"
        assert result['double_chance_bought_today'] is True
        assert result['prediction_exists'] is True
    finally:
        # Restore original function
        shop_service.get_or_create_player_effects = original_get_effects
    game_id_1 = 1
    game_id_2 = 2
    user_id = 1

    # Mock no existing effects for both games
    mock_result = MagicMock()
    mock_result.first.return_value = None
    mock_db_session.exec.return_value = mock_result

    # Execute - create effects for same user in different games
    effect_1 = get_or_create_player_effects(mock_db_session, game_id_1, user_id)
    effect_2 = get_or_create_player_effects(mock_db_session, game_id_2, user_id)

    # Verify both effects were created
    assert mock_db_session.add.call_count == 2

    # Verify effects have different game_ids
    added_effect_1 = mock_db_session.add.call_args_list[0][0][0]
    added_effect_2 = mock_db_session.add.call_args_list[1][0][0]

    assert added_effect_1.game_id == game_id_1
    assert added_effect_1.user_id == user_id

    assert added_effect_2.game_id == game_id_2
    assert added_effect_2.user_id == user_id

    # Verify they are different objects
    assert added_effect_1 != added_effect_2
