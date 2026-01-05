"""Tests for PidorCoinTransaction model."""
import pytest
from datetime import datetime
from bot.app.models import PidorCoinTransaction, Game, TGUser


class TestPidorCoinTransaction:
    """Test cases for PidorCoinTransaction model."""

    def test_create_transaction(self, mock_db_session, mock_game, mock_tg_user):
        """Test creating a PidorCoinTransaction record."""
        # Create transaction
        transaction = PidorCoinTransaction(
            game_id=mock_game.id,
            user_id=mock_tg_user.id,
            amount=1,
            year=2024,
            reason="pidor_win",
            created_at=datetime.utcnow()
        )

        # Verify fields
        assert transaction.game_id == mock_game.id
        assert transaction.user_id == mock_tg_user.id
        assert transaction.amount == 1
        assert transaction.year == 2024
        assert transaction.reason == "pidor_win"
        assert isinstance(transaction.created_at, datetime)

    def test_transaction_relationships(self, mock_db_session, mock_game, mock_tg_user):
        """Test relationships with Game and TGUser."""
        # Create transaction
        transaction = PidorCoinTransaction(
            game_id=mock_game.id,
            user_id=mock_tg_user.id,
            amount=1,
            year=2024,
            reason="pidor_win"
        )

        # Verify relationships are accessible
        assert hasattr(transaction, 'game')
        assert hasattr(transaction, 'user')

    def test_unique_constraint(self, mock_db_session, mock_game, mock_tg_user):
        """Test unique constraint on (game_id, user_id, year)."""
        # Check that __table_args__ contains the unique constraint
        table_args = PidorCoinTransaction.__table_args__
        assert table_args is not None

        # Find the unique constraint
        unique_constraint = None
        for arg in table_args:
            if hasattr(arg, 'name') and arg.name == 'idx_game_user_year':
                unique_constraint = arg
                break

        assert unique_constraint is not None
        assert hasattr(unique_constraint, 'columns')
        assert len(unique_constraint.columns) == 3
        assert 'game_id' in [col.name for col in unique_constraint.columns]
        assert 'user_id' in [col.name for col in unique_constraint.columns]
        assert 'year' in [col.name for col in unique_constraint.columns]

    def test_required_fields(self, mock_db_session, mock_game, mock_tg_user):
        """Test that required fields are properly set."""
        # Create transaction with all required fields
        transaction = PidorCoinTransaction(
            game_id=mock_game.id,
            user_id=mock_tg_user.id,
            amount=1,
            year=2024,
            reason="pidor_win"
        )

        # Verify all fields are set
        assert transaction.game_id is not None
        assert transaction.user_id is not None
        assert transaction.amount is not None
        assert transaction.year is not None
        assert transaction.reason is not None
        assert transaction.created_at is not None

    def test_negative_amount(self, mock_db_session, mock_game, mock_tg_user):
        """Test that negative amounts are allowed (for future debit functionality)."""
        transaction = PidorCoinTransaction(
            game_id=mock_game.id,
            user_id=mock_tg_user.id,
            amount=-1,
            year=2024,
            reason="penalty"
        )

        assert transaction.amount == -1

    def test_different_reasons(self, mock_db_session, mock_game, mock_tg_user):
        """Test transaction with different reason types."""
        reasons = ["pidor_win", "bonus", "penalty", "transfer"]

        for reason in reasons:
            transaction = PidorCoinTransaction(
                game_id=mock_game.id,
                user_id=mock_tg_user.id,
                amount=1,
                year=2024,
                reason=reason
            )

            assert transaction.reason == reason
