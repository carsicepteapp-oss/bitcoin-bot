"""In-memory rolling candle buffer."""
from __future__ import annotations

import logging
from collections import deque
from typing import Deque, List, Optional

from app.models.candle import Candle

logger = logging.getLogger(__name__)


class CandleBuffer:
    """Thread-unsafe rolling window of the most recent N candles.

    New candles are appended; the oldest ones are automatically evicted
    once the buffer reaches *max_size*.
    """

    def __init__(self, max_size: int = 200) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self._max_size = max_size
        self._data: Deque[Candle] = deque(maxlen=max_size)

    # ── Mutators ──────────────────────────────────────────────────────────────

    def append(self, candle: Candle) -> None:
        """Add a single candle, evicting the oldest if at capacity."""
        self._data.append(candle)

    def extend(self, candles: List[Candle]) -> None:
        """Append a list of candles in order."""
        for candle in candles:
            self._data.append(candle)

    def seed(self, candles: List[Candle]) -> None:
        """Replace the entire buffer content (used on startup)."""
        self._data.clear()
        self.extend(candles[-self._max_size :])
        logger.debug("Buffer seeded with %d candles", len(self._data))

    def update_or_append(self, candle: Candle) -> None:
        """Update the last candle if same timestamp, else append."""
        if self._data and self._data[-1].timestamp == candle.timestamp:
            self._data[-1] = candle
        else:
            self.append(candle)

    # ── Accessors ─────────────────────────────────────────────────────────────

    def latest(self) -> Optional[Candle]:
        """Return the most recent candle, or None if empty."""
        return self._data[-1] if self._data else None

    def last_n(self, n: int) -> List[Candle]:
        """Return the last *n* candles as a list (oldest → newest)."""
        data = list(self._data)
        return data[-n:] if n <= len(data) else data

    def closes(self, n: Optional[int] = None) -> List[float]:
        """Return close prices for the last *n* candles."""
        candles = self.last_n(n) if n is not None else list(self._data)
        return [c.close for c in candles]

    def highs(self, n: Optional[int] = None) -> List[float]:
        candles = self.last_n(n) if n is not None else list(self._data)
        return [c.high for c in candles]

    def lows(self, n: Optional[int] = None) -> List[float]:
        candles = self.last_n(n) if n is not None else list(self._data)
        return [c.low for c in candles]

    def volumes(self, n: Optional[int] = None) -> List[float]:
        candles = self.last_n(n) if n is not None else list(self._data)
        return [c.volume for c in candles]

    def all_candles(self) -> List[Candle]:
        """Return a snapshot of all candles (oldest → newest)."""
        return list(self._data)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._data)

    @property
    def max_size(self) -> int:
        return self._max_size

    def is_ready(self, min_candles: int) -> bool:
        """True if the buffer has at least *min_candles* entries."""
        return len(self._data) >= min_candles

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"CandleBuffer(size={len(self._data)}/{self._max_size})"
