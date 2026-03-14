"""Paper trade state machine for a single 5-minute window."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.models.signal import Decision, MarketRegime, SignalResult
from app.models.trade import TradeRecord


@dataclass
class OpenTrade:
    """Represents a paper trade that has been opened but not yet resolved."""

    trade_id: int
    window_start: datetime
    window_end: datetime
    open_price: float
    decision: Decision
    confidence: float
    regime: MarketRegime
    signal_scores: dict
    reason: str
    stake: float
    opened_at: datetime = field(default_factory=datetime.utcnow)


def resolve_trade(
    open_trade: OpenTrade,
    close_price: float,
    balance_after: float,
    pnl: float,
    is_correct: Optional[bool],
    notes: str = "",
) -> TradeRecord:
    """Convert an OpenTrade into a resolved TradeRecord.

    Args:
        open_trade:    The pending trade to resolve.
        close_price:   BTC close price at window end.
        balance_after: Virtual balance after PnL applied.
        pnl:           Realised PnL for this trade.
        is_correct:    True/False/None (None for NO_TRADE).
        notes:         Optional free-text annotation.
    """
    actual_outcome: Optional[Decision]
    if open_trade.decision == Decision.NO_TRADE:
        actual_outcome = None
    elif close_price >= open_trade.open_price:
        actual_outcome = Decision.UP
    else:
        actual_outcome = Decision.DOWN

    return TradeRecord(
        id=open_trade.trade_id,
        window_start=open_trade.window_start,
        window_end=open_trade.window_end,
        open_price=open_trade.open_price,
        close_price=close_price,
        decision=open_trade.decision,
        actual_outcome=actual_outcome,
        confidence=open_trade.confidence,
        regime=open_trade.regime,
        signal_scores=open_trade.signal_scores,
        reason=open_trade.reason,
        stake=open_trade.stake,
        pnl=pnl,
        balance_after=balance_after,
        is_correct=is_correct,
        notes=notes,
    )
