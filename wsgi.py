"""WSGI entry point for gunicorn — starts bot engine then exposes Flask app."""
from __future__ import annotations

import logging
import os
import threading

from app.config import get_config
from app.web import server as web_server
from app.web.state import BotState
from app.web.log_handler import WebLogHandler
from app.web.notifier import WebNotifier
from app.logger import setup_logging

cfg = get_config()
cfg.ensure_dirs()
setup_logging(level=cfg.output.log_level, log_dir=cfg.output.log_dir)

state = BotState(initial_balance=cfg.risk.initial_balance)
state.is_running = True

web_handler = WebLogHandler(state)
web_handler.setFormatter(
    logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
logging.getLogger().addHandler(web_handler)

web_server.set_state(state)

from app.data.binance_provider import BinanceProvider
from app.reporting.reporter import Reporter
from app.simulation.engine import LiveSimulationEngine

provider = BinanceProvider(timeout_sec=cfg.data.request_timeout_sec)
notifier = WebNotifier(state)
reporter = Reporter(cfg)
engine = LiveSimulationEngine(cfg, provider, notifier, reporter)

bot_thread = threading.Thread(target=engine.run, daemon=True, name="BotEngine")
bot_thread.start()

# gunicorn looks for `app` or `application`
app = web_server.flask_app
