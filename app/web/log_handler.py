"""Custom logging handler that pushes log lines into BotState."""
from __future__ import annotations

import logging

from app.web.state import BotState


class WebLogHandler(logging.Handler):
    """Appends formatted log records to BotState.logs."""

    def __init__(self, state: BotState) -> None:
        super().__init__()
        self._state = state

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            self._state.add_log(line)
        except Exception:
            self.handleError(record)
