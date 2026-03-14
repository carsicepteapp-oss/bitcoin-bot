"""Abstract notifier interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from app.models.signal import SignalResult
from app.models.trade import TradeRecord


class BaseNotifier(ABC):
    """Interface for trade event notifications."""

    @abstractmethod
    def on_decision(
        self,
        result: SignalResult,
        stake: float,
        open_price: float,
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        """Called when a decision is made at window open."""

    @abstractmethod
    def on_resolution(self, record: TradeRecord) -> None:
        """Called when a trade is resolved at window close."""

    def on_tick(self, current_price: float, window_end: Optional[datetime]) -> None:
        """Called every polling tick with the latest price. Override if needed."""
