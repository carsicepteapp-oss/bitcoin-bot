"""Risk manager — controls stake sizing, cooldown, and daily loss limits."""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from app.config import RiskConfig
from app.models.signal import Decision
from app.utils.math_utils import clamp

logger = logging.getLogger(__name__)


class RiskManager:
    """Stateful risk controller for paper trading.

    Responsibilities:
    - Compute allowed stake for the next trade.
    - Track consecutive losses and enforce cooldown.
    - Enforce the daily maximum loss limit.
    - Reduce stake after a loss streak.
    """

    def __init__(self, cfg: RiskConfig) -> None:
        self._cfg = cfg
        self._balance: float = cfg.initial_balance

        # Loss tracking
        self._consecutive_losses: int = 0
        self._cooldown_remaining: int = 0

        # Daily loss tracking
        self._daily_pnl: float = 0.0
        self._today: date = date.today()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def balance(self) -> float:
        return self._balance

    def compute_stake(self, decision: Decision) -> float:
        """Return the stake to use for the next trade.

        Returns 0.0 when trading is blocked (daily loss / cooldown).
        """
        if decision == Decision.NO_TRADE:
            return 0.0

        self._refresh_daily_counter()

        if self._is_daily_limit_hit():
            logger.warning("Daily loss limit hit. Skipping trade.")
            return 0.0

        if self._cooldown_remaining > 0:
            logger.info("Cooldown active (%d windows remaining). Skipping.", self._cooldown_remaining)
            return 0.0

        stake = self._base_stake()

        # Reduce stake after consecutive losses
        if self._consecutive_losses > 0:
            reduction = self._cfg.loss_reduction_factor ** self._consecutive_losses
            stake = stake * clamp(reduction, 0.1, 1.0)

        stake = clamp(stake, 0.0, self._balance)
        logger.debug("Stake computed: %.2f (consecutive_losses=%d)", stake, self._consecutive_losses)
        return stake

    def record_result(self, pnl: float, is_correct: Optional[bool]) -> None:
        """Update internal state after a window resolves.

        Args:
            pnl:        Realised PnL (positive = profit, negative = loss).
            is_correct: True if prediction was correct, False if wrong,
                        None for NO_TRADE.
        """
        self._refresh_daily_counter()

        self._balance += pnl
        self._daily_pnl += pnl

        if is_correct is None:
            # NO_TRADE — do not touch streak
            return

        if is_correct:
            self._consecutive_losses = 0
            self._cooldown_remaining = 0
            logger.debug("Win recorded. Streak reset. Balance=%.2f", self._balance)
        else:
            self._consecutive_losses += 1
            logger.debug(
                "Loss recorded. Streak=%d. Balance=%.2f",
                self._consecutive_losses,
                self._balance,
            )
            if self._consecutive_losses >= self._cfg.max_consecutive_losses:
                self._cooldown_remaining = self._cfg.cooldown_windows
                logger.warning(
                    "Max consecutive losses (%d) reached. Cooldown: %d windows.",
                    self._cfg.max_consecutive_losses,
                    self._cooldown_remaining,
                )

        # Decrement cooldown after each evaluated window
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1

    def apply_slippage(self, stake: float) -> float:
        """Return the effective cost deducted for slippage/fees."""
        return stake * (self._cfg.slippage_pct / 100.0)

    def compute_pnl(self, stake: float, is_correct: bool) -> float:
        """Calculate realised PnL for a trade.

        Assumes a 1:1 payout (win=+stake, lose=-stake) minus slippage.
        """
        slippage = self.apply_slippage(stake)
        if is_correct:
            return stake - slippage
        return -(stake + slippage)

    # ── Queries ───────────────────────────────────────────────────────────────

    @property
    def daily_pnl(self) -> float:
        return self._daily_pnl

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    @property
    def is_in_cooldown(self) -> bool:
        return self._cooldown_remaining > 0

    # ── Private ───────────────────────────────────────────────────────────────

    def _base_stake(self) -> float:
        if self._cfg.stake_mode == "percent":
            return self._balance * (self._cfg.stake_percent / 100.0)
        return self._cfg.stake_fixed

    def _is_daily_limit_hit(self) -> bool:
        return self._daily_pnl <= -abs(self._cfg.max_daily_loss)

    def _refresh_daily_counter(self) -> None:
        today = date.today()
        if today != self._today:
            logger.info("New day detected. Resetting daily PnL.")
            self._daily_pnl = 0.0
            self._today = today
