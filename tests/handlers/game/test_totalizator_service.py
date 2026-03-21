"""Tests for totalizator service."""
import pytest
from unittest.mock import MagicMock, patch, call

from bot.app.models import Totalizator, TotalizatorBet, ChatBank
from bot.handlers.game.totalizator_service import (
    create_totalizator,
    get_open_totalizators,
    get_expired_unresolved,
    get_user_open_totalizators,
    get_totalizator_bets,
    has_user_bet,
    place_bet,
    resolve_totalizator,
)


def _make_totalizator(**kwargs):
    defaults = dict(
        id=1,
        game_id=10,
        creator_id=100,
        title="Тест",
        stake=10,
        option_yes="За",
        option_no="Против",
        deadline_year=2026,
        deadline_day=200,
        status="open",
        message_id=None,
    )
    defaults.update(kwargs)
    tot = MagicMock(spec=Totalizator)
    for k, v in defaults.items():
        setattr(tot, k, v)
    return tot


def _make_bet(totalizator_id=1, user_id=1, choice="yes"):
    bet = MagicMock(spec=TotalizatorBet)
    bet.totalizator_id = totalizator_id
    bet.user_id = user_id
    bet.choice = choice
    return bet


@pytest.mark.unit
class TestCreateTotalizator:
    def test_creates_and_returns(self, mock_db_session):
        tot = create_totalizator(mock_db_session, 10, 100, "Спор", 15, 2026, 180)
        assert isinstance(tot, Totalizator)
        assert tot.game_id == 10
        assert tot.creator_id == 100
        assert tot.title == "Спор"
        assert tot.stake == 15
        assert tot.status == "open"
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()


@pytest.mark.unit
class TestGetOpenTotalizators:
    def test_returns_open_list(self, mock_db_session):
        open_tots = [_make_totalizator(), _make_totalizator(id=2)]
        mock_result = MagicMock()
        mock_result.all.return_value = open_tots
        mock_db_session.exec.return_value = mock_result

        result = get_open_totalizators(mock_db_session, 10)
        assert result == open_tots

    def test_empty_when_none(self, mock_db_session):
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_db_session.exec.return_value = mock_result

        result = get_open_totalizators(mock_db_session, 10)
        assert result == []


@pytest.mark.unit
class TestGetExpiredUnresolved:
    def test_expired_before_current(self, mock_db_session):
        tot = _make_totalizator(deadline_year=2026, deadline_day=50)
        mock_result = MagicMock()
        mock_result.all.return_value = [tot]
        mock_db_session.exec.return_value = mock_result

        result = get_expired_unresolved(mock_db_session, 10, 2026, 100)
        assert tot in result

    def test_not_expired_today(self, mock_db_session):
        tot = _make_totalizator(deadline_year=2026, deadline_day=100)
        mock_result = MagicMock()
        mock_result.all.return_value = [tot]
        mock_db_session.exec.return_value = mock_result

        # deadline_day == current_day — не истёк (истекает строго <)
        result = get_expired_unresolved(mock_db_session, 10, 2026, 100)
        assert tot not in result

    def test_not_expired_future(self, mock_db_session):
        tot = _make_totalizator(deadline_year=2026, deadline_day=200)
        mock_result = MagicMock()
        mock_result.all.return_value = [tot]
        mock_db_session.exec.return_value = mock_result

        result = get_expired_unresolved(mock_db_session, 10, 2026, 100)
        assert tot not in result

    def test_multiple_mixed(self, mock_db_session):
        expired = _make_totalizator(id=1, deadline_year=2026, deadline_day=50)
        active = _make_totalizator(id=2, deadline_year=2026, deadline_day=200)
        mock_result = MagicMock()
        mock_result.all.return_value = [expired, active]
        mock_db_session.exec.return_value = mock_result

        result = get_expired_unresolved(mock_db_session, 10, 2026, 100)
        assert expired in result
        assert active not in result


@pytest.mark.unit
class TestHasUserBet:
    def test_returns_true_when_bet_exists(self, mock_db_session):
        mock_result = MagicMock()
        mock_result.first.return_value = _make_bet()
        mock_db_session.exec.return_value = mock_result

        assert has_user_bet(mock_db_session, 1, 1) is True

    def test_returns_false_when_no_bet(self, mock_db_session):
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db_session.exec.return_value = mock_result

        assert has_user_bet(mock_db_session, 1, 1) is False


@pytest.mark.unit
class TestPlaceBet:
    @patch('bot.handlers.game.totalizator_service.calculate_commission_amount')
    @patch('bot.handlers.game.totalizator_service.spend_coins')
    @patch('bot.handlers.game.totalizator_service._get_or_create_chat_bank')
    def test_deducts_stake_adds_commission_to_bank(
        self, mock_bank_fn, mock_spend, mock_calc, mock_db_session
    ):
        mock_calc.return_value = 2  # commission=2, effective=8
        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_bank_fn.return_value = mock_bank

        tot = _make_totalizator(stake=10)
        place_bet(mock_db_session, tot, user_id=42, choice="yes", year=2026)

        mock_spend.assert_called_once_with(
            mock_db_session, 10, 42, 10, 2026, "totalizator_bet", auto_commit=False
        )
        assert mock_bank.balance == 2  # комиссия добавлена в банк

    @patch('bot.handlers.game.totalizator_service.calculate_commission_amount')
    @patch('bot.handlers.game.totalizator_service.spend_coins')
    @patch('bot.handlers.game.totalizator_service._get_or_create_chat_bank')
    def test_creates_bet_record(self, mock_bank_fn, mock_spend, mock_calc, mock_db_session):
        mock_calc.return_value = 1
        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_bank_fn.return_value = mock_bank

        tot = _make_totalizator(stake=5)
        place_bet(mock_db_session, tot, user_id=7, choice="no", year=2026)

        added = [c.args[0] for c in mock_db_session.add.call_args_list]
        bets = [o for o in added if isinstance(o, TotalizatorBet)]
        assert len(bets) == 1
        assert bets[0].user_id == 7
        assert bets[0].choice == "no"


@pytest.mark.unit
class TestResolveTotalizator:
    def _setup_bets(self, mock_db_session, bets):
        mock_result = MagicMock()
        mock_result.all.return_value = bets
        mock_db_session.exec.return_value = mock_result

    @patch('bot.handlers.game.totalizator_service.calculate_commission_amount')
    @patch('bot.handlers.game.totalizator_service.add_coins')
    @patch('bot.handlers.game.totalizator_service._get_or_create_chat_bank')
    def test_winners_get_pot(self, mock_bank_fn, mock_add, mock_calc, mock_db_session):
        """Победители делят пул поровну."""
        mock_calc.return_value = 2  # commission=2, effective=8
        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_bank_fn.return_value = mock_bank

        bets = [
            _make_bet(user_id=1, choice="yes"),
            _make_bet(user_id=2, choice="yes"),
            _make_bet(user_id=3, choice="no"),
        ]
        self._setup_bets(mock_db_session, bets)

        tot = _make_totalizator(stake=10)  # effective=8, pot=8*3=24, per_winner=24//2=12
        result = resolve_totalizator(mock_db_session, tot, "yes", 2026)

        assert result['cancelled'] is False
        assert result['refunded'] is False
        assert result['per_winner'] == 12
        assert len(result['winners']) == 2
        assert len(result['losers']) == 1

        # Победители получили по 12
        add_calls = mock_add.call_args_list
        winner_calls = [c for c in add_calls if c.args[3] == 12]
        assert len(winner_calls) == 2

    @patch('bot.handlers.game.totalizator_service.calculate_commission_amount')
    @patch('bot.handlers.game.totalizator_service.add_coins')
    @patch('bot.handlers.game.totalizator_service._get_or_create_chat_bank')
    def test_remainder_goes_to_bank(self, mock_bank_fn, mock_add, mock_calc, mock_db_session):
        """Остаток от деления идёт в банк."""
        mock_calc.return_value = 1  # commission=1, effective=9
        mock_bank = MagicMock()
        mock_bank.balance = 0
        mock_bank_fn.return_value = mock_bank

        # pot = 9*3=27, 2 победителя, per_winner=13, remainder=1
        bets = [
            _make_bet(user_id=1, choice="yes"),
            _make_bet(user_id=2, choice="yes"),
            _make_bet(user_id=3, choice="no"),
        ]
        self._setup_bets(mock_db_session, bets)

        tot = _make_totalizator(stake=10)
        resolve_totalizator(mock_db_session, tot, "yes", 2026)

        assert mock_bank.balance == 1  # remainder в банк

    @patch('bot.handlers.game.totalizator_service.calculate_commission_amount')
    @patch('bot.handlers.game.totalizator_service.add_coins')
    @patch('bot.handlers.game.totalizator_service._get_or_create_chat_bank')
    def test_cancel_refunds_effective(self, mock_bank_fn, mock_add, mock_calc, mock_db_session):
        """При отмене каждый получает effective = stake - commission."""
        mock_calc.return_value = 2  # commission=2, effective=8
        mock_bank_fn.return_value = MagicMock()

        bets = [_make_bet(user_id=1, choice="yes"), _make_bet(user_id=2, choice="no")]
        self._setup_bets(mock_db_session, bets)

        tot = _make_totalizator(stake=10)
        result = resolve_totalizator(mock_db_session, tot, "cancel", 2026)

        assert result['cancelled'] is True
        assert result['effective'] == 8
        assert result['commission'] == 2

        # Все получили по 8
        add_calls = mock_add.call_args_list
        refund_calls = [c for c in add_calls if c.args[3] == 8]
        assert len(refund_calls) == 2

    @patch('bot.handlers.game.totalizator_service.calculate_commission_amount')
    @patch('bot.handlers.game.totalizator_service.add_coins')
    @patch('bot.handlers.game.totalizator_service._get_or_create_chat_bank')
    def test_all_one_side_refunds(self, mock_bank_fn, mock_add, mock_calc, mock_db_session):
        """Если все на одной стороне — ставки возвращаются."""
        mock_calc.return_value = 2  # effective=8
        mock_bank_fn.return_value = MagicMock()

        bets = [_make_bet(user_id=1, choice="yes"), _make_bet(user_id=2, choice="yes")]
        self._setup_bets(mock_db_session, bets)

        tot = _make_totalizator(stake=10)
        result = resolve_totalizator(mock_db_session, tot, "yes", 2026)

        assert result['refunded'] is True
        assert result['cancelled'] is False

        add_calls = mock_add.call_args_list
        refund_calls = [c for c in add_calls if c.args[3] == 8]
        assert len(refund_calls) == 2

    @patch('bot.handlers.game.totalizator_service.calculate_commission_amount')
    @patch('bot.handlers.game.totalizator_service.add_coins')
    @patch('bot.handlers.game.totalizator_service._get_or_create_chat_bank')
    def test_status_updated_to_resolved(self, mock_bank_fn, mock_add, mock_calc, mock_db_session):
        """Статус тотализатора обновляется после завершения."""
        mock_calc.return_value = 1
        mock_bank_fn.return_value = MagicMock()

        bets = [_make_bet(user_id=1, choice="yes"), _make_bet(user_id=2, choice="no")]
        self._setup_bets(mock_db_session, bets)

        tot = _make_totalizator(stake=5)
        resolve_totalizator(mock_db_session, tot, "yes", 2026)

        assert tot.status == "resolved_yes"
        assert tot.resolved_at is not None

    @patch('bot.handlers.game.totalizator_service.calculate_commission_amount')
    @patch('bot.handlers.game.totalizator_service.add_coins')
    @patch('bot.handlers.game.totalizator_service._get_or_create_chat_bank')
    def test_no_bets_cancel_is_safe(self, mock_bank_fn, mock_add, mock_calc, mock_db_session):
        """Отмена тотализатора без ставок не падает."""
        mock_calc.return_value = 1
        mock_bank_fn.return_value = MagicMock()

        self._setup_bets(mock_db_session, [])

        tot = _make_totalizator(stake=5)
        result = resolve_totalizator(mock_db_session, tot, "cancel", 2026)

        assert result['cancelled'] is True
        mock_add.assert_not_called()
