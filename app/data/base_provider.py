"""Abstract base class for market data providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.models.candle import Candle


class BaseDataProvider(ABC):
    """Interface every data provider must implement."""

    @abstractmethod
    def fetch_candles(self, symbol: str, interval: str, limit: int) -> List[Candle]:
        """Fetch the most recent *limit* closed candles for *symbol*.

        Args:
            symbol:   Trading pair, e.g. "BTCUSDT".
            interval: Candle interval string, e.g. "1m".
            limit:    Number of candles to retrieve (most recent first).

        Returns:
            List of Candle objects sorted oldest → newest.

        Raises:
            DataProviderError: on network or parsing failure.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""


class DataProviderError(Exception):
    """Raised when a data provider cannot fulfil a request."""
