"""Polymarket Gamma API — find the active BTC 5-minute Up/Down market."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import requests

logger = logging.getLogger(__name__)

_GAMMA_API = "https://gamma-api.polymarket.com"
_REQUEST_TIMEOUT = 10
_WINDOW_SECONDS = 300  # 5 minutes


@dataclass
class BTCMarket:
    """Relevant fields of a single BTC Up/Down 5-minute Polymarket market."""

    condition_id: str
    up_token_id: str
    down_token_id: str
    up_price: float      # current market price for UP token (0–1)
    down_price: float    # current market price for DOWN token (0–1)
    window_start_ts: int
    window_end_ts: int
    slug: str

    @property
    def window_start(self) -> datetime:
        return datetime.fromtimestamp(self.window_start_ts, tz=timezone.utc)

    @property
    def window_end(self) -> datetime:
        return datetime.fromtimestamp(self.window_end_ts, tz=timezone.utc)


def find_current_btc_market(window_start: Optional[datetime] = None) -> Optional[BTCMarket]:
    """Find the currently active (or next) BTC 5-minute Up/Down market.

    Args:
        window_start: Optional explicit window start time. If None, uses now.

    Returns:
        BTCMarket or None if not found.
    """
    if window_start is not None:
        base_ts = int(window_start.timestamp())
    else:
        now_ts = int(time.time())
        base_ts = (now_ts // _WINDOW_SECONDS) * _WINDOW_SECONDS

    # Try current window, then next, then previous
    candidates = [base_ts, base_ts + _WINDOW_SECONDS, base_ts - _WINDOW_SECONDS]

    for ts in candidates:
        slug = f"btc-updown-5m-{ts}"
        market = _fetch_market_by_slug(slug, ts)
        if market is not None:
            logger.info("Found Polymarket market: %s | UP=%.3f DOWN=%.3f",
                        slug, market.up_price, market.down_price)
            return market

    logger.warning("No active BTC 5-minute market found for ts=%d", base_ts)
    return None


def _fetch_market_by_slug(slug: str, window_ts: int) -> Optional[BTCMarket]:
    """Query Gamma API for an event by slug and parse the result."""
    try:
        resp = requests.get(
            f"{_GAMMA_API}/events",
            params={"slug": slug},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("Gamma API request failed for slug=%s: %s", slug, exc)
        return None

    if not data:
        return None

    event = data[0] if isinstance(data, list) else data
    markets: List[dict] = event.get("markets", [])
    if not markets:
        return None

    mkt = markets[0]

    try:
        condition_id: str = mkt["conditionId"]
        outcomes: List[str] = mkt.get("outcomes", ["Up", "Down"])
        token_ids: List[str] = mkt.get("clobTokenIds", [])
        prices_raw: List[str] = mkt.get("outcomePrices", ["0.5", "0.5"])

        if len(token_ids) < 2:
            logger.warning("Market %s has fewer than 2 tokens", slug)
            return None

        # Outcomes are ordered: outcomes[0]=Up → token_ids[0]=UP token
        up_idx = next((i for i, o in enumerate(outcomes) if o.lower() == "up"), 0)
        down_idx = 1 - up_idx

        up_price = float(prices_raw[up_idx])
        down_price = float(prices_raw[down_idx])

        # Clamp prices to valid range
        up_price = max(0.01, min(0.99, up_price))
        down_price = max(0.01, min(0.99, down_price))

        return BTCMarket(
            condition_id=condition_id,
            up_token_id=token_ids[up_idx],
            down_token_id=token_ids[down_idx],
            up_price=up_price,
            down_price=down_price,
            window_start_ts=window_ts,
            window_end_ts=window_ts + _WINDOW_SECONDS,
            slug=slug,
        )
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Failed to parse market data for slug=%s: %s", slug, exc)
        return None
