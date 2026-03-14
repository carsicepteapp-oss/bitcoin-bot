"""Web notifier -- pushes bot events into BotState for the dashboard."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.models.signal import SignalResult
from app.models.trade import TradeRecord
from app.notifier.base_notifier import BaseNotifier
from app.web.state import BotState


class WebNotifier(BaseNotifier):
    def __init__(self, state: BotState) -> None:
        self._state = state

    def on_decision(self, result, stake, open_price, window_start, window_end):
        self._state.update_decision(
            decision=result.decision.value,
            confidence=result.confidence,
            regime=result.regime.value,
            price=open_price,
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            stake=stake,
        )

    def on_resolution(self, record: TradeRecord) -> None:
        self._state.add_trade(record.to_dict())

    def on_tick(self, current_price: float, window_end: Optional[datetime]) -> None:
        with self._state._lock:
            self._state.current_price = current_price
            if window_end:
                self._state.window_end = window_end.isoformat()
