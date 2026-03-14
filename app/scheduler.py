"""Window scheduler utilities (used internally by the live engine)."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Callable, Optional

from app.utils.time_utils import (
    floor_to_window,
    seconds_until_next_window,
    utcnow,
    WINDOW_MINUTES,
)

logger = logging.getLogger(__name__)


class WindowScheduler:
    """Utility that calls a callback at every 5-minute boundary.

    This is an alternative to the polling-based approach in LiveSimulationEngine.
    Usage:
        scheduler = WindowScheduler(on_window_start=my_callback)
        scheduler.run()
    """

    def __init__(
        self,
        on_window_start: Callable[[datetime], None],
        window_minutes: int = WINDOW_MINUTES,
        pre_window_sleep_sec: float = 0.5,
    ) -> None:
        self._callback = on_window_start
        self._window_minutes = window_minutes
        self._pre_sleep = pre_window_sleep_sec

    def run(self) -> None:
        """Block and call the callback at every window boundary."""
        logger.info("Scheduler started. Window=%dm.", self._window_minutes)
        while True:
            secs = seconds_until_next_window(self._window_minutes)
            logger.debug("Sleeping %.1f s until next window…", secs)
            # Sleep in small increments to remain responsive to Ctrl+C
            self._interruptible_sleep(secs)
            window_start = floor_to_window(utcnow(), self._window_minutes)
            try:
                self._callback(window_start)
            except Exception as exc:
                logger.exception("Callback raised an unhandled exception: %s", exc)

    # ── Private ───────────────────────────────────────────────────────────────

    def _interruptible_sleep(self, total_secs: float) -> None:
        """Sleep in 1-second chunks so KeyboardInterrupt is handled promptly."""
        elapsed = 0.0
        while elapsed < total_secs:
            chunk = min(1.0, total_secs - elapsed)
            time.sleep(chunk)
            elapsed += chunk
