"""Performance metrics computed from a list of TradeRecords."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.models.signal import Decision, MarketRegime
from app.models.trade import TradeRecord
from app.utils.math_utils import safe_div


@dataclass
class PerformanceMetrics:
    """Aggregated performance statistics."""

    total_windows: int = 0
    traded_windows: int = 0
    no_trade_windows: int = 0

    wins: int = 0
    losses: int = 0
    accuracy: float = 0.0       # wins / traded_windows
    win_rate: float = 0.0       # same as accuracy
    no_trade_rate: float = 0.0  # no_trade / total

    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0  # gross_profit / abs(gross_loss)

    max_drawdown: float = 0.0
    peak_balance: float = 0.0
    final_balance: float = 0.0

    avg_confidence: float = 0.0
    avg_stake: float = 0.0

    regime_accuracy: Dict[str, float] = field(default_factory=dict)
    hour_accuracy: Dict[int, float] = field(default_factory=dict)
    daily_summary: Dict[str, float] = field(default_factory=dict)  # date → pnl


def compute_metrics(records: List[TradeRecord], initial_balance: float) -> PerformanceMetrics:
    """Compute all performance metrics from resolved TradeRecords."""
    if not records:
        return PerformanceMetrics()

    m = PerformanceMetrics()
    m.total_windows = len(records)

    traded = [r for r in records if r.decision != Decision.NO_TRADE and r.stake > 0]
    no_trade = [r for r in records if r.decision == Decision.NO_TRADE or r.stake == 0]

    m.traded_windows = len(traded)
    m.no_trade_windows = len(no_trade)
    m.no_trade_rate = safe_div(m.no_trade_windows, m.total_windows) * 100

    correct = [r for r in traded if r.is_correct is True]
    wrong = [r for r in traded if r.is_correct is False]

    m.wins = len(correct)
    m.losses = len(wrong)
    m.accuracy = safe_div(m.wins, m.traded_windows) * 100
    m.win_rate = m.accuracy

    m.total_pnl = sum(r.pnl for r in records)
    m.gross_profit = sum(r.pnl for r in records if r.pnl > 0)
    m.gross_loss = sum(r.pnl for r in records if r.pnl < 0)
    m.profit_factor = safe_div(m.gross_profit, abs(m.gross_loss))

    # Drawdown
    balance = initial_balance
    peak = initial_balance
    max_dd = 0.0
    for r in records:
        balance += r.pnl
        if balance > peak:
            peak = balance
        dd = peak - balance
        if dd > max_dd:
            max_dd = dd
    m.max_drawdown = max_dd
    m.peak_balance = peak
    m.final_balance = records[-1].balance_after if records else initial_balance

    if traded:
        m.avg_confidence = sum(r.confidence for r in traded) / len(traded)
        m.avg_stake = sum(r.stake for r in traded) / len(traded)

    # Regime breakdown
    m.regime_accuracy = _regime_accuracy(traded)

    # Hour breakdown
    m.hour_accuracy = _hour_accuracy(traded)

    # Daily PnL
    m.daily_summary = _daily_pnl(records)

    return m


def _regime_accuracy(traded: List[TradeRecord]) -> Dict[str, float]:
    by_regime: Dict[str, List[bool]] = {}
    for r in traded:
        key = r.regime.value
        by_regime.setdefault(key, []).append(bool(r.is_correct))
    return {
        regime: safe_div(sum(outcomes), len(outcomes)) * 100
        for regime, outcomes in by_regime.items()
    }


def _hour_accuracy(traded: List[TradeRecord]) -> Dict[int, float]:
    by_hour: Dict[int, List[bool]] = {}
    for r in traded:
        h = r.window_start.hour
        by_hour.setdefault(h, []).append(bool(r.is_correct))
    return {
        h: safe_div(sum(outcomes), len(outcomes)) * 100
        for h, outcomes in sorted(by_hour.items())
    }


def _daily_pnl(records: List[TradeRecord]) -> Dict[str, float]:
    by_day: Dict[str, float] = {}
    for r in records:
        day = r.window_start.date().isoformat()
        by_day[day] = by_day.get(day, 0.0) + r.pnl
    return by_day
