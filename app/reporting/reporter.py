"""Reporter — saves trade records and prints performance summaries."""
from __future__ import annotations

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from app.config import AppConfig
from app.models.trade import TradeRecord
from app.reporting.metrics import PerformanceMetrics, compute_metrics

logger = logging.getLogger(__name__)

_CSV_FIELDNAMES = [
    "id", "timestamp", "window_start", "window_end",
    "open_price", "close_price", "decision", "actual_outcome",
    "confidence", "regime", "stake", "pnl", "balance_after",
    "is_correct", "reason", "notes",
]


class Reporter:
    """Handles CSV/JSON persistence and console reporting."""

    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._reports_dir = cfg.output.reports_dir
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        self._session_tag = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self._csv_path = self._reports_dir / f"trades_{self._session_tag}.csv"
        self._csv_initialized = False

    # ── Live append (called after each resolved trade) ────────────────────────

    def append_record(self, record: TradeRecord) -> None:
        """Append a single record to the running CSV file."""
        row = record.to_dict()
        row.pop("signal_scores", None)  # keep CSV flat

        if not self._csv_initialized:
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES, extrasaction="ignore")
                writer.writeheader()
            self._csv_initialized = True

        with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES, extrasaction="ignore")
            writer.writerow(row)

    # ── Bulk save (called at session end or backtest complete) ────────────────

    def save_records(self, records: List[TradeRecord]) -> None:
        """Save all records to CSV and JSON."""
        if not records:
            logger.info("No records to save.")
            return

        # CSV
        csv_path = self._reports_dir / f"trades_{self._session_tag}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES, extrasaction="ignore")
            writer.writeheader()
            for r in records:
                row = r.to_dict()
                row.pop("signal_scores", None)
                writer.writerow(row)
        logger.info("CSV saved → %s", csv_path)

        # JSON (with signal_scores)
        json_path = self._reports_dir / f"trades_{self._session_tag}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([r.to_dict() for r in records], f, indent=2, ensure_ascii=False)
        logger.info("JSON saved → %s", json_path)

    # ── Console summary ───────────────────────────────────────────────────────

    def print_summary(
        self,
        records: List[TradeRecord],
        initial_balance: Optional[float] = None,
    ) -> None:
        """Print a formatted performance summary to stdout."""
        if initial_balance is None:
            initial_balance = self._cfg.risk.initial_balance

        m = compute_metrics(records, initial_balance)
        self._print_metrics(m)

    def load_and_print_report(self) -> None:
        """Load the most recent JSON report and print its summary."""
        json_files = sorted(self._reports_dir.glob("trades_*.json"))
        if not json_files:
            print("No report files found in", self._reports_dir)
            return

        latest = json_files[-1]
        logger.info("Loading report: %s", latest)
        with open(latest, encoding="utf-8") as f:
            data = json.load(f)

        records = self._deserialize(data)
        self.print_summary(records)

    # ── Private ───────────────────────────────────────────────────────────────

    def _print_metrics(self, m: PerformanceMetrics) -> None:
        sep = "─" * 54
        print(f"\n{'═' * 54}")
        print(f"  PERFORMANCE SUMMARY")
        print(f"{'═' * 54}")
        print(f"  Windows total     : {m.total_windows}")
        print(f"  Traded            : {m.traded_windows}")
        print(f"  NO TRADE          : {m.no_trade_windows}  ({m.no_trade_rate:.1f}%)")
        print(sep)
        print(f"  Wins / Losses     : {m.wins} / {m.losses}")
        print(f"  Accuracy          : {m.accuracy:.1f}%")
        print(f"  Profit Factor     : {m.profit_factor:.2f}")
        print(sep)
        print(f"  Total PnL         : {m.total_pnl:+.2f}")
        print(f"  Gross Profit      : {m.gross_profit:.2f}")
        print(f"  Gross Loss        : {m.gross_loss:.2f}")
        print(f"  Max Drawdown      : {m.max_drawdown:.2f}")
        print(f"  Peak Balance      : {m.peak_balance:.2f}")
        print(f"  Final Balance     : {m.final_balance:.2f}")
        print(sep)
        print(f"  Avg Confidence    : {m.avg_confidence:.1f}")
        print(f"  Avg Stake         : {m.avg_stake:.2f}")
        print(sep)

        if m.regime_accuracy:
            print("  Accuracy by Regime:")
            for regime, acc in sorted(m.regime_accuracy.items()):
                print(f"    {regime:<22}: {acc:.1f}%")
            print(sep)

        if m.hour_accuracy:
            print("  Accuracy by Hour (UTC):")
            for hour, acc in m.hour_accuracy.items():
                print(f"    {hour:02d}:00            : {acc:.1f}%")
            print(sep)

        if m.daily_summary:
            print("  Daily PnL:")
            for day, pnl in sorted(m.daily_summary.items()):
                print(f"    {day}       : {pnl:+.2f}")

        print(f"{'═' * 54}\n")

    def _deserialize(self, data: list) -> List[TradeRecord]:
        """Reconstruct TradeRecord objects from JSON dicts (best-effort)."""
        from app.models.signal import Decision, MarketRegime
        records = []
        for d in data:
            try:
                records.append(
                    TradeRecord(
                        id=d["id"],
                        window_start=datetime.fromisoformat(d["window_start"]),
                        window_end=datetime.fromisoformat(d["window_end"]),
                        open_price=d["open_price"],
                        close_price=d.get("close_price"),
                        decision=Decision(d["decision"]),
                        actual_outcome=Decision(d["actual_outcome"]) if d.get("actual_outcome") else None,
                        confidence=d["confidence"],
                        regime=MarketRegime(d["regime"]),
                        signal_scores=d.get("signal_scores", {}),
                        reason=d.get("reason", ""),
                        stake=d["stake"],
                        pnl=d["pnl"],
                        balance_after=d["balance_after"],
                        is_correct=d.get("is_correct"),
                        notes=d.get("notes", ""),
                        timestamp=datetime.fromisoformat(d["timestamp"]),
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed record: %s", exc)
        return records
