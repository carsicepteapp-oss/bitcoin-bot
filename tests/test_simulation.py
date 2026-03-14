"""Unit tests for simulation components."""
from datetime import datetime, timezone, timedelta
import pytest

from app.models.signal import Decision, MarketRegime
from app.simulation.paper_trade import OpenTrade, resolve_trade
from app.reporting.metrics import compute_metrics
from app.models.trade import TradeRecord


def _make_open_trade(decision=Decision.UP, stake=10.0) -> OpenTrade:
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    return OpenTrade(
        trade_id=1,
        window_start=now,
        window_end=now + timedelta(minutes=5),
        open_price=50000.0,
        decision=decision,
        confidence=65.0,
        regime=MarketRegime.TREND_UP,
        signal_scores={"ema": 0.5},
        reason="test",
        stake=stake,
    )


class TestPaperTrade:
    def test_resolve_win(self):
        trade = _make_open_trade(Decision.UP)
        record = resolve_trade(
            open_trade=trade,
            close_price=50100.0,   # price went UP
            balance_after=1010.0,
            pnl=10.0,
            is_correct=True,
        )
        assert record.actual_outcome == Decision.UP
        assert record.is_correct is True
        assert record.pnl == 10.0

    def test_resolve_loss(self):
        trade = _make_open_trade(Decision.UP)
        record = resolve_trade(
            open_trade=trade,
            close_price=49900.0,   # price went DOWN (wrong prediction)
            balance_after=990.0,
            pnl=-10.0,
            is_correct=False,
        )
        assert record.actual_outcome == Decision.DOWN
        assert record.is_correct is False

    def test_resolve_no_trade(self):
        trade = _make_open_trade(Decision.NO_TRADE, stake=0.0)
        record = resolve_trade(
            open_trade=trade,
            close_price=50000.0,
            balance_after=1000.0,
            pnl=0.0,
            is_correct=None,
        )
        assert record.actual_outcome is None
        assert record.pnl == 0.0

    def test_to_dict_serializable(self):
        trade = _make_open_trade()
        record = resolve_trade(trade, 50100.0, 1010.0, 10.0, True)
        d = record.to_dict()
        assert isinstance(d, dict)
        assert d["decision"] == "UP"
        assert d["pnl"] == 10.0


class TestMetrics:
    def _make_record(self, decision, is_correct, pnl, balance_after, regime=MarketRegime.SIDEWAYS):
        now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        actual = Decision.UP if is_correct else Decision.DOWN if decision == Decision.UP else Decision.UP
        if decision == Decision.NO_TRADE:
            actual = None
        return TradeRecord(
            id=1, window_start=now, window_end=now + timedelta(minutes=5),
            open_price=50000.0, close_price=50100.0,
            decision=decision, actual_outcome=actual,
            confidence=60.0, regime=regime,
            signal_scores={}, reason="test",
            stake=10.0 if decision != Decision.NO_TRADE else 0.0,
            pnl=pnl, balance_after=balance_after,
            is_correct=is_correct,
        )

    def test_empty_records(self):
        m = compute_metrics([], initial_balance=1000.0)
        assert m.total_windows == 0

    def test_perfect_accuracy(self):
        records = [self._make_record(Decision.UP, True, 10.0, 1010.0 + i * 10) for i in range(5)]
        m = compute_metrics(records, initial_balance=1000.0)
        assert m.accuracy == pytest.approx(100.0)
        assert m.wins == 5
        assert m.losses == 0

    def test_total_pnl(self):
        records = [
            self._make_record(Decision.UP, True, 10.0, 1010.0),
            self._make_record(Decision.UP, False, -10.0, 1000.0),
            self._make_record(Decision.NO_TRADE, None, 0.0, 1000.0),
        ]
        m = compute_metrics(records, initial_balance=1000.0)
        assert m.total_pnl == pytest.approx(0.0)
        assert m.traded_windows == 2
        assert m.no_trade_windows == 1

    def test_profit_factor(self):
        records = [
            self._make_record(Decision.UP, True, 20.0, 1020.0),
            self._make_record(Decision.UP, False, -10.0, 1010.0),
        ]
        m = compute_metrics(records, initial_balance=1000.0)
        assert m.profit_factor == pytest.approx(2.0)
