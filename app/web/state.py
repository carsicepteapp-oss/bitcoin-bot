"""Shared thread-safe state between the bot engine and the Flask server."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import List, Optional


class BotState:
    """All data the dashboard needs, protected by a lock."""

    def __init__(self, initial_balance: float = 1000.0, save_path: Optional[Path] = None) -> None:
        self._lock = threading.Lock()
        self._save_path = save_path
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.trades: List[dict] = []
        self.logs: List[str] = []
        self.last_decision: str = "–"
        self.last_confidence: float = 0.0
        self.last_regime: str = "–"
        self.current_price: float = 0.0
        self.prev_price: float = 0.0
        self.window_start: Optional[str] = None
        self.window_end: Optional[str] = None
        self.is_running: bool = False
        # Active bet info
        self.current_stake: float = 0.0
        # Last resolved result (shown as toast, cleared after being read once)
        self.last_result: Optional[dict] = None
        self._result_read: bool = False
        # Active manual bet (placed via dashboard, resolved by server thread)
        self.open_manual_bet: Optional[dict] = None

    # ── Disk persistence ──────────────────────────────────────────────────────

    def load_from_disk(self) -> None:
        """Restore trades and balance from the last saved session."""
        if self._save_path is None or not self._save_path.exists():
            return
        try:
            data = json.loads(self._save_path.read_text(encoding="utf-8"))
            with self._lock:
                self.initial_balance = data.get("initial_balance", self.initial_balance)
                self.balance = data.get("balance", self.balance)
                loaded = data.get("trades", [])
                self.trades = loaded[-200:] if len(loaded) > 200 else loaded
        except Exception:
            pass  # Corrupt / missing file — start fresh

    def save_to_disk(self) -> None:
        """Persist current trades and balance to disk (called inside lock)."""
        if self._save_path is None:
            return
        try:
            data = {
                "initial_balance": self.initial_balance,
                "balance": self.balance,
                "trades": self.trades,
            }
            self._save_path.write_text(
                json.dumps(data, default=str, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── Bot engine updates ────────────────────────────────────────────────────

    def update_decision(
        self,
        decision: str,
        confidence: float,
        regime: str,
        price: float,
        window_start: str,
        window_end: str,
        stake: float = 0.0,
    ) -> None:
        with self._lock:
            self.prev_price = self.current_price if self.current_price else price
            self.current_price = price
            self._result_read = False
            # If a manual bet is active, don't overwrite its display info
            if self.open_manual_bet is not None:
                return
            self.last_decision = decision
            self.last_confidence = confidence
            self.last_regime = regime
            self.window_start = window_start
            self.window_end = window_end
            self.current_stake = stake

    def add_trade(self, trade_dict: dict) -> None:
        with self._lock:
            self.trades.append(trade_dict)
            # Support both absolute balance_after and delta-pnl records
            if "balance_after" in trade_dict:
                self.balance = trade_dict["balance_after"]
            else:
                self.balance = round(self.balance + trade_dict.get("pnl", 0.0), 2)
                trade_dict["balance_after"] = self.balance
            self.current_stake = 0.0
            if trade_dict.get("decision") not in (None, "NO_TRADE") and trade_dict.get("stake", 0) > 0:
                self.last_result = {
                    "is_correct": trade_dict.get("is_correct"),
                    "pnl": trade_dict.get("pnl", 0.0),
                    "decision": trade_dict.get("decision"),
                    "stake": trade_dict.get("stake", 0.0),
                    "open_price": trade_dict.get("open_price"),
                    "close_price": trade_dict.get("close_price"),
                }
            if len(self.trades) > 200:
                self.trades = self.trades[-200:]
            self.save_to_disk()

    def add_log(self, line: str) -> None:
        with self._lock:
            self.logs.append(line)
            if len(self.logs) > 300:
                self.logs = self.logs[-300:]

    # ── Manual bet ────────────────────────────────────────────────────────────

    def place_manual_bet(
        self,
        trade_id: int,
        direction: str,
        stake: float,
        entry_price: float,
        window_start_iso: str,
        window_end_iso: str,
    ) -> None:
        """Record a manual bet and make it visible on the dashboard."""
        with self._lock:
            self.open_manual_bet = {
                "trade_id": trade_id,
                "direction": direction,
                "stake": stake,
                "entry_price": entry_price,
                "window_start_iso": window_start_iso,
                "window_end_iso": window_end_iso,
            }
            # Show in Active Bet card
            self.last_decision = direction
            self.last_confidence = 100.0
            self.last_regime = "MANUAL"
            self.window_start = window_start_iso
            self.window_end = window_end_iso
            self.current_stake = stake
            self.prev_price = self.current_price if self.current_price else entry_price

    def resolve_manual_bet(self, close_price: float) -> Optional[dict]:
        """Resolve the open manual bet and return the trade record, or None."""
        with self._lock:
            bet = self.open_manual_bet
            if bet is None:
                return None
            self.open_manual_bet = None

        entry = bet["entry_price"]
        direction = bet["direction"]
        stake = bet["stake"]

        actual_up = close_price >= entry
        predicted_up = direction == "UP"
        is_correct = actual_up == predicted_up
        pnl = round(stake if is_correct else -stake, 2)

        trade_dict = {
            "id": bet["trade_id"],
            "window_start": bet["window_start_iso"],
            "window_end": bet["window_end_iso"],
            "open_price": entry,
            "close_price": close_price,
            "decision": direction,
            "actual_outcome": "UP" if actual_up else "DOWN",
            "confidence": 100.0,
            "regime": "MANUAL",
            "signal_scores": {},
            "reason": "Manuel bahis",
            "stake": stake,
            "pnl": pnl,
            "is_correct": is_correct,
            "notes": "manuel",
        }
        self.add_trade(trade_dict)
        # Reset display fields after manual bet resolves
        with self._lock:
            self.last_decision = "–"
            self.last_confidence = 0.0
            self.last_regime = "–"
        return trade_dict

    # ── Serialise for dashboard ───────────────────────────────────────────────

    def to_dict(self) -> dict:
        with self._lock:
            traded = [t for t in self.trades if t.get("decision") != "NO_TRADE" and t.get("stake", 0) > 0]
            wins = sum(1 for t in traded if t.get("is_correct") is True)
            win_rate = round(wins / len(traded) * 100, 1) if traded else 0.0
            pnl = round(self.balance - self.initial_balance, 2)
            pnl_pct = round(pnl / self.initial_balance * 100, 2) if self.initial_balance else 0.0
            balance_history = [t["balance_after"] for t in self.trades[-40:] if "balance_after" in t]
            result_snapshot = self.last_result
            if result_snapshot is not None:
                self.last_result = None
            has_manual = self.open_manual_bet is not None
            return {
                "balance": round(self.balance, 2),
                "initial_balance": round(self.initial_balance, 2),
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "win_rate": win_rate,
                "total_trades": len(traded),
                "trades": list(self.trades),
                "logs": list(self.logs),
                "last_decision": self.last_decision,
                "last_confidence": self.last_confidence,
                "last_regime": self.last_regime,
                "current_price": self.current_price,
                "prev_price": self.prev_price,
                "window_start": self.window_start,
                "window_end": self.window_end,
                "is_running": self.is_running,
                "balance_history": balance_history,
                "current_stake": round(self.current_stake, 2),
                "last_result": result_snapshot,
                "has_manual_bet": has_manual,
            }
