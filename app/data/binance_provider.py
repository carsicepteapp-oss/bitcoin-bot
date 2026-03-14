"""Binance public REST API data provider (no authentication required)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import requests

from app.data.base_provider import BaseDataProvider, DataProviderError
from app.models.candle import Candle

_BINANCE_BASE_URL = "https://api.binance.com"
_KLINES_ENDPOINT = "/api/v3/klines"

# Binance kline response column indices
_IDX_OPEN_TIME = 0
_IDX_OPEN = 1
_IDX_HIGH = 2
_IDX_LOW = 3
_IDX_CLOSE = 4
_IDX_VOLUME = 5

logger = logging.getLogger(__name__)


class BinanceProvider(BaseDataProvider):
    """Fetches OHLCV data from Binance public klines endpoint."""

    def __init__(self, timeout_sec: int = 10) -> None:
        self._timeout = timeout_sec
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    @property
    def name(self) -> str:
        return "binance"

    def fetch_candles(self, symbol: str, interval: str, limit: int) -> List[Candle]:
        """Fetch up to *limit* closed 1m candles from Binance.

        The most-recent candle may still be open, so it is dropped.
        """
        url = f"{_BINANCE_BASE_URL}{_KLINES_ENDPOINT}"
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit + 1,  # +1 so we can discard the open candle
        }

        try:
            response = self._session.get(url, params=params, timeout=self._timeout)
            response.raise_for_status()
            raw: list = response.json()
        except requests.RequestException as exc:
            raise DataProviderError(f"Binance request failed: {exc}") from exc
        except ValueError as exc:
            raise DataProviderError(f"Failed to parse Binance response: {exc}") from exc

        # Drop the last (potentially open) candle
        raw = raw[:-1]

        candles: List[Candle] = []
        for row in raw:
            try:
                candles.append(
                    Candle(
                        timestamp=datetime.fromtimestamp(
                            row[_IDX_OPEN_TIME] / 1000, tz=timezone.utc
                        ),
                        open=float(row[_IDX_OPEN]),
                        high=float(row[_IDX_HIGH]),
                        low=float(row[_IDX_LOW]),
                        close=float(row[_IDX_CLOSE]),
                        volume=float(row[_IDX_VOLUME]),
                    )
                )
            except (IndexError, ValueError, TypeError) as exc:
                logger.warning("Skipping malformed candle row: %s – %s", row, exc)

        logger.debug("Fetched %d candles for %s %s", len(candles), symbol, interval)
        return candles

    def close(self) -> None:
        """Release the underlying HTTP session."""
        self._session.close()
