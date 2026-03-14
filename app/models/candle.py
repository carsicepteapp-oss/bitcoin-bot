"""OHLCV candle data model."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Candle:
    """Represents a single OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def mid(self) -> float:
        """Midpoint of the candle range."""
        return (self.high + self.low) / 2.0

    @property
    def range(self) -> float:
        """High-low range."""
        return self.high - self.low

    @property
    def body(self) -> float:
        """Absolute candle body size."""
        return abs(self.close - self.open)

    @property
    def is_bullish(self) -> bool:
        """True if close >= open."""
        return self.close >= self.open

    @property
    def body_ratio(self) -> float:
        """Body as fraction of total range. Returns 0 if range is 0."""
        if self.range == 0:
            return 0.0
        return self.body / self.range

    @property
    def upper_shadow(self) -> float:
        """Upper shadow size."""
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        """Lower shadow size."""
        return min(self.open, self.close) - self.low
