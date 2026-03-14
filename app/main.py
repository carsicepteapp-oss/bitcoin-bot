"""Entry point — CLI for live simulation, backtest, report, and web commands.

Usage:
    python -m app.main live
    python -m app.main web
    python -m app.main backtest --file data/btc_1m.csv
    python -m app.main report
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from app.config import get_config
from app.logger import setup_logging
from app.models.candle import Candle

logger = logging.getLogger(__name__)


# ── CLI argument parser ───────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="btc-predictor",
        description="BTC 5-minute Up/Down paper trading predictor",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # live
    subparsers.add_parser("live", help="Run live paper-trading simulation (terminal only)")

    # web
    web = subparsers.add_parser("web", help="Run live simulation with browser dashboard")
    web.add_argument("--port", type=int, default=5000, help="Dashboard port (default 5000)")
    web.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")

    # backtest
    bt = subparsers.add_parser("backtest", help="Run backtest on historical data")
    bt.add_argument(
        "--file",
        type=Path,
        required=True,
        help="Path to CSV file with columns: timestamp,open,high,low,close,volume",
    )

    # report
    subparsers.add_parser("report", help="Print latest saved report")

    return parser


# ── Command handlers ──────────────────────────────────────────────────────────

def cmd_live() -> None:
    """Start the live paper-trading simulation (terminal only)."""
    cfg = get_config()
    cfg.ensure_dirs()
    setup_logging(level=cfg.output.log_level, log_dir=cfg.output.log_dir)

    from app.data.binance_provider import BinanceProvider
    from app.notifier.mock_notifier import MockNotifier
    from app.reporting.reporter import Reporter
    from app.simulation.engine import LiveSimulationEngine

    provider = BinanceProvider(timeout_sec=cfg.data.request_timeout_sec)
    notifier = MockNotifier()
    reporter = Reporter(cfg)

    engine = LiveSimulationEngine(cfg, provider, notifier, reporter)
    engine.run()


def cmd_web(port: int = 5000, open_browser: bool = True) -> None:
    """Start the live simulation with a browser dashboard."""
    import threading
    import webbrowser
    import time

    cfg = get_config()
    cfg.ensure_dirs()

    from app.web.state import BotState
    from app.web.log_handler import WebLogHandler
    from app.web.notifier import WebNotifier
    from app.web import server as web_server
    from app.data.binance_provider import BinanceProvider
    from app.reporting.reporter import Reporter
    from app.simulation.engine import LiveSimulationEngine

    # Shared state — persisted to disk so history survives restarts
    from pathlib import Path as _Path
    _state_file = _Path(cfg.output.data_dir) / "bot_state.json"
    state = BotState(initial_balance=cfg.risk.initial_balance, save_path=_state_file)
    state.load_from_disk()   # restore previous trades/balance if any
    state.is_running = True

    # Setup logging — send to both file and web state
    setup_logging(level=cfg.output.log_level, log_dir=cfg.output.log_dir)
    web_handler = WebLogHandler(state)
    web_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )
    logging.getLogger().addHandler(web_handler)

    # Wire state into Flask
    web_server.set_state(state)

    # Build engine with WebNotifier
    provider = BinanceProvider(timeout_sec=cfg.data.request_timeout_sec)
    notifier = WebNotifier(state)
    reporter = Reporter(cfg)
    engine = LiveSimulationEngine(cfg, provider, notifier, reporter)

    # Run engine in background thread
    bot_thread = threading.Thread(target=engine.run, daemon=True, name="BotEngine")
    bot_thread.start()

    # Open browser after short delay
    if open_browser:
        def _open():
            time.sleep(1.5)
            webbrowser.open(f"http://127.0.0.1:{port}")
        threading.Thread(target=_open, daemon=True).start()

    print(f"\n  Dashboard: http://127.0.0.1:{port}")
    print("  Durdurmak icin: Ctrl+C\n")

    # On cloud (Railway etc.) bind to all interfaces; locally stay on loopback
    import os as _os
    host = "0.0.0.0" if _os.environ.get("PORT") else "127.0.0.1"

    # Flask runs in main thread (blocking)
    web_server.run_server(host=host, port=port)


def cmd_backtest(file: Path) -> None:
    """Run a backtest using historical candles from *file*."""
    cfg = get_config()
    cfg.ensure_dirs()
    setup_logging(level=cfg.output.log_level, log_dir=cfg.output.log_dir)

    if not file.exists():
        logger.error("File not found: %s", file)
        sys.exit(1)

    candles = _load_csv(file)
    if not candles:
        logger.error("No candles loaded from %s", file)
        sys.exit(1)

    logger.info("Loaded %d candles from %s", len(candles), file)

    from app.reporting.reporter import Reporter
    from app.simulation.engine import BacktestEngine

    reporter = Reporter(cfg)
    engine = BacktestEngine(cfg, reporter)
    engine.run(candles)


def cmd_report() -> None:
    """Print the most recent saved report."""
    cfg = get_config()
    cfg.ensure_dirs()
    setup_logging(level=cfg.output.log_level, log_dir=cfg.output.log_dir)

    from app.reporting.reporter import Reporter
    reporter = Reporter(cfg)
    reporter.load_and_print_report()


# ── CSV loader ────────────────────────────────────────────────────────────────

def _load_csv(path: Path) -> List[Candle]:
    """Load OHLCV candles from a CSV file.

    Expected columns (order-independent): timestamp,open,high,low,close,volume
    Timestamp formats accepted:
      - ISO 8601 string: "2024-01-01T00:00:00Z" or "2024-01-01 00:00:00"
      - Unix timestamp (seconds or milliseconds as integer/float)
    """
    candles: List[Candle] = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            try:
                ts = _parse_timestamp(row["timestamp"])
                candles.append(
                    Candle(
                        timestamp=ts,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0.0)),
                    )
                )
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Skipping row %d: %s — %s", i + 1, row, exc)

    return sorted(candles, key=lambda c: c.timestamp)


def _parse_timestamp(raw: str) -> datetime:
    raw = raw.strip()
    # Try ISO format
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass
    # Try unix timestamp
    try:
        ts_float = float(raw)
        if ts_float > 1e12:  # milliseconds
            ts_float /= 1000
        return datetime.fromtimestamp(ts_float, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        pass
    raise ValueError(f"Cannot parse timestamp: {raw!r}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "live":
        cmd_live()
    elif args.command == "web":
        cmd_web(port=args.port, open_browser=not args.no_browser)
    elif args.command == "backtest":
        cmd_backtest(args.file)
    elif args.command == "report":
        cmd_report()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
