"""Time utility helpers."""
from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

WINDOW_MINUTES = 5


def utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(tz=timezone.utc)


def floor_to_window(dt: datetime, window_minutes: int = WINDOW_MINUTES) -> datetime:
    """Floor *dt* down to the nearest N-minute boundary.

    Example: 08:17:43 → 08:15:00 for window_minutes=5.
    """
    total_seconds = window_minutes * 60
    ts = int(dt.timestamp())
    floored_ts = (ts // total_seconds) * total_seconds
    return datetime.fromtimestamp(floored_ts, tz=timezone.utc)


def next_window_start(dt: datetime, window_minutes: int = WINDOW_MINUTES) -> datetime:
    """Return the start of the next N-minute window after *dt*."""
    current_floor = floor_to_window(dt, window_minutes)
    return current_floor + timedelta(minutes=window_minutes)


def seconds_until_next_window(window_minutes: int = WINDOW_MINUTES) -> float:
    """Return seconds remaining until the next window boundary."""
    now = utcnow()
    nxt = next_window_start(now, window_minutes)
    return (nxt - now).total_seconds()


def window_end(window_start: datetime, window_minutes: int = WINDOW_MINUTES) -> datetime:
    """Return the end timestamp of a window given its start."""
    return window_start + timedelta(minutes=window_minutes)


def is_new_window(
    last_window: datetime | None,
    window_minutes: int = WINDOW_MINUTES,
) -> tuple[bool, datetime]:
    """Check whether the current time is in a new window vs *last_window*.

    Returns (is_new, current_window_start).
    """
    now = utcnow()
    current_window = floor_to_window(now, window_minutes)
    if last_window is None or current_window > last_window:
        return True, current_window
    return False, current_window


def sleep_until_next_window(window_minutes: int = WINDOW_MINUTES) -> None:
    """Block until the start of the next N-minute window."""
    seconds = seconds_until_next_window(window_minutes)
    time.sleep(max(0.0, seconds))
