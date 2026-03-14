"""Mock notifier -- logs events; replace with Telegram/Slack as needed."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.models.signal import SignalResult
from app.models.trade import TradeRecord
from app.notifier.base_notifier import BaseNotifier

logger = logging.getLogger(__name__)


class MockNotifier(BaseNotifier):
    def on_decision(self, result, stake, open_price, window_start, window_end):
        logger.info(
            "[NOTIFY] Decision=%s | conf=%.1f | stake=%.2f | price=%.2f | %s",
            result.decision.value, result.confidence, stake, open_price, result.reason,
        )

    def on_resolution(self, record):
        outcome = "WIN" if record.is_correct else ("LOSS" if record.is_correct is False else "SKIP")
        logger.info(
            "[NOTIFY] %s | PnL=%+.2f | balance=%.2f | open=%.2f -> close=%.2f",
            outcome, record.pnl, record.balance_after, record.open_price, record.close_price or 0.0,
        )
