"""Simulation engines — Live and Backtest modes."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

from app.config import AppConfig
from app.data.base_provider import BaseDataProvider, DataProviderError
from app.data.buffer import CandleBuffer
from app.features.extractor import FeatureExtractor
from app.models.candle import Candle
from app.models.signal import Decision
from app.models.trade import TradeRecord
from app.notifier.base_notifier import BaseNotifier
from app.regime.detector import RegimeDetector
from app.reporting.reporter import Reporter
from app.risk.manager import RiskManager
from app.simulation.paper_trade import OpenTrade, resolve_trade
from app.strategy.ensemble import EnsembleDecisionEngine
from app.polymarket.market_finder import find_current_btc_market
from app.utils.time_utils import (
    floor_to_window,
    is_new_window,
    next_window_start,
    utcnow,
    window_end,
)

logger = logging.getLogger(__name__)


class LiveSimulationEngine:
    """Runs the paper-trading loop against real-time Binance data.

    Lifecycle per 5-minute window:
      1. Detect window start.
      2. Fetch candles → extract features → decide.
      3. Record open trade.
      4. Wait until window ends.
      5. Fetch close price → resolve trade → update risk manager.
      6. Notify → save → repeat.
    """

    def __init__(
        self,
        cfg: AppConfig,
        provider: BaseDataProvider,
        notifier: BaseNotifier,
        reporter: Reporter,
    ) -> None:
        self._cfg = cfg
        self._provider = provider
        self._notifier = notifier
        self._reporter = reporter

        self._buffer = CandleBuffer(cfg.data.buffer_size)
        self._extractor = FeatureExtractor(cfg.features)
        self._regime_detector = RegimeDetector()
        self._engine = EnsembleDecisionEngine(
            cfg.strategy, cfg.volatility_filter, self._regime_detector
        )
        self._risk = RiskManager(cfg.risk)
        self._trade_counter = 0
        self._last_window: Optional[datetime] = None
        self._open_trade: Optional[OpenTrade] = None
        self._records: List[TradeRecord] = []

        # Polymarket real-bet integration (optional)
        self._poly_trader = None
        if cfg.polymarket.enabled:
            self._init_polymarket_trader()

    def _init_polymarket_trader(self) -> None:
        """Instantiate the Polymarket trader (only if private key is configured)."""
        try:
            from app.polymarket.trader import PolymarketTrader
            self._poly_trader = PolymarketTrader(self._cfg.polymarket.private_key)
            logger.info("Polymarket trader initialised. Real bets enabled.")
        except Exception as exc:
            logger.error("Polymarket trader init failed: %s", exc)
            self._poly_trader = None

    def run(self) -> None:
        """Start the live simulation loop. Blocks indefinitely."""
        logger.info("=" * 60)
        logger.info("Live simulation started. Press Ctrl+C to stop.")
        logger.info("Balance: %.2f | Symbol: %s", self._risk.balance, self._cfg.data.symbol)
        logger.info("=" * 60)

        self._seed_buffer()

        try:
            while True:
                self._tick()
                time.sleep(self._cfg.data.polling_interval_sec)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
        finally:
            self._reporter.save_records(self._records)
            self._reporter.print_summary(self._records)

    # ── Private ───────────────────────────────────────────────────────────────

    def _seed_buffer(self) -> None:
        """Fetch initial candles to fill the buffer before first decision."""
        logger.info("Seeding buffer with %d candles...", self._cfg.data.buffer_size)
        try:
            candles = self._provider.fetch_candles(
                self._cfg.data.symbol,
                self._cfg.data.candle_interval,
                self._cfg.data.buffer_size,
            )
            self._buffer.seed(candles)
            logger.info("Buffer ready: %d candles", self._buffer.size)
        except DataProviderError as exc:
            logger.error("Failed to seed buffer: %s", exc)

    def _tick(self) -> None:
        """Single polling tick."""
        now = utcnow()

        # ── Check if a pending trade just closed ──────────────────────────────
        if self._open_trade is not None and now >= self._open_trade.window_end:
            self._resolve_open_trade()

        # ── Check if a new window just started ───────────────────────────────
        new_window, current_window = is_new_window(self._last_window)
        if new_window:
            self._last_window = current_window
            self._on_window_start(current_window)

        # ── Always refresh buffer + notify dashboard of latest price ──────────
        self._refresh_buffer()
        latest = self._buffer.latest()
        if latest:
            w_end = self._open_trade.window_end if self._open_trade else None
            self._notifier.on_tick(latest.close, w_end)

    def _refresh_buffer(self) -> None:
        try:
            candles = self._provider.fetch_candles(
                self._cfg.data.symbol,
                self._cfg.data.candle_interval,
                limit=5,
            )
            for c in candles:
                self._buffer.update_or_append(c)
        except DataProviderError as exc:
            logger.warning("Buffer refresh failed: %s", exc)

    def _on_window_start(self, window_start: datetime) -> None:
        """Make a prediction at the start of a new 5-minute window."""
        w_end = window_end(window_start)
        logger.info(
            ">> New window: %s -> %s",
            window_start.strftime("%H:%M"),
            w_end.strftime("%H:%M"),
        )

        if not self._buffer.is_ready(self._cfg.strategy.min_candles_required):
            logger.warning("Buffer not ready. Skipping window.")
            return

        features = self._extractor.extract(self._buffer)
        if features is None:
            logger.warning("Feature extraction failed. Skipping window.")
            return

        result = self._engine.decide(features)
        open_price = features.current_price
        stake = self._risk.compute_stake(result.decision)

        self._trade_counter += 1
        self._open_trade = OpenTrade(
            trade_id=self._trade_counter,
            window_start=window_start,
            window_end=w_end,
            open_price=open_price,
            decision=result.decision,
            confidence=result.confidence,
            regime=result.regime,
            signal_scores=result.signal_scores,
            reason=result.reason,
            stake=stake,
        )

        self._notifier.on_decision(result, stake, open_price, window_start, w_end)
        logger.info(
            "  Decision: %-10s | Conf: %5.1f | Stake: %.2f | Price: %.2f",
            result.decision.value,
            result.confidence,
            stake,
            open_price,
        )

        # ── Place real Polymarket bet ─────────────────────────────────────────
        if self._poly_trader is not None and result.decision != Decision.NO_TRADE:
            self._place_polymarket_bet(result.decision, window_start)

    def _place_polymarket_bet(self, decision: Decision, window_start: datetime) -> None:
        """Find the active Polymarket market and place a real bet."""
        try:
            market = find_current_btc_market(window_start)
            if market is None:
                logger.warning("Polymarket: no active market found for window %s", window_start)
                return

            balance = self._poly_trader.get_usdc_balance()
            usdc_stake = balance * (self._cfg.polymarket.stake_pct / 100.0)
            if usdc_stake < self._cfg.polymarket.min_stake_usdc:
                logger.warning(
                    "Polymarket: stake %.2f USDC below minimum %.2f. Skipping.",
                    usdc_stake,
                    self._cfg.polymarket.min_stake_usdc,
                )
                return

            if decision == Decision.UP:
                token_id = market.up_token_id
                price = market.up_price
            else:
                token_id = market.down_token_id
                price = market.down_price

            logger.info(
                "Polymarket: placing %s bet | market=%s | usdc=%.2f | price=%.3f",
                decision.value,
                market.slug,
                usdc_stake,
                price,
            )
            bet = self._poly_trader.place_bet(token_id, price, usdc_stake)
            if bet.success:
                logger.info(
                    "Polymarket: bet placed | order_id=%s | shares=%.2f | usdc=%.2f",
                    bet.order_id,
                    bet.shares,
                    bet.usdc_spent,
                )
            else:
                logger.error("Polymarket: bet failed | %s", bet.error)
        except Exception as exc:
            logger.error("Polymarket bet error: %s", exc)

    def _resolve_open_trade(self) -> None:
        """Evaluate the open trade now that the window has closed."""
        trade = self._open_trade
        assert trade is not None

        close_price = self._get_close_price(trade.window_end)
        if close_price is None:
            logger.warning("Could not fetch close price. Resolving with open price.")
            close_price = trade.open_price

        is_correct: Optional[bool]
        pnl: float

        if trade.decision == Decision.NO_TRADE or trade.stake == 0.0:
            is_correct = None
            pnl = 0.0
        else:
            actual_up = close_price >= trade.open_price
            predicted_up = trade.decision == Decision.UP
            is_correct = actual_up == predicted_up
            pnl = self._risk.compute_pnl(trade.stake, is_correct)

        self._risk.record_result(pnl, is_correct)

        record = resolve_trade(
            open_trade=trade,
            close_price=close_price,
            balance_after=self._risk.balance,
            pnl=pnl,
            is_correct=is_correct,
        )
        self._records.append(record)
        self._reporter.append_record(record)
        self._notifier.on_resolution(record)

        outcome_str = "WIN" if is_correct else ("LOSS" if is_correct is False else "SKIP")
        logger.info(
            "  %s Resolved: open=%.2f close=%.2f | PnL=%+.2f | Balance=%.2f",
            outcome_str,
            trade.open_price,
            close_price,
            pnl,
            self._risk.balance,
        )
        self._open_trade = None

    def _get_close_price(self, at: datetime) -> Optional[float]:
        try:
            candles = self._provider.fetch_candles(
                self._cfg.data.symbol, self._cfg.data.candle_interval, limit=3
            )
            if candles:
                return candles[-1].close
        except DataProviderError as exc:
            logger.warning("Failed to fetch close price: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Backtest Engine
# ─────────────────────────────────────────────────────────────────────────────


class BacktestEngine:
    """Replays historical 1-minute candles through the full pipeline.

    Supports CSV input with columns: timestamp, open, high, low, close, volume.
    5-minute windows are created synthetically from the 1-minute bars.
    There is NO lookahead bias: the decision at window start only uses candles
    that were closed before that timestamp.
    """

    _WINDOW_MINUTES = 5

    def __init__(self, cfg: AppConfig, reporter: Reporter) -> None:
        self._cfg = cfg
        self._reporter = reporter

        self._extractor = FeatureExtractor(cfg.features)
        self._regime_detector = RegimeDetector()
        self._engine = EnsembleDecisionEngine(
            cfg.strategy, cfg.volatility_filter, self._regime_detector
        )
        self._risk = RiskManager(cfg.risk)

    def run(self, candles: List[Candle]) -> List[TradeRecord]:
        """Run the full backtest on *candles* and return trade records."""
        if not candles:
            logger.error("No candles provided for backtest.")
            return []

        logger.info(
            "Backtest started: %d candles | %s -> %s",
            len(candles),
            candles[0].timestamp.strftime("%Y-%m-%d %H:%M"),
            candles[-1].timestamp.strftime("%Y-%m-%d %H:%M"),
        )

        records: List[TradeRecord] = []
        buffer = CandleBuffer(self._cfg.data.buffer_size)
        trade_counter = 0

        # Group candles into 5-minute windows
        windows = self._group_into_windows(candles)
        logger.info("Total 5-minute windows: %d", len(windows))

        for window_start, window_candles in windows:
            w_end = window_start + timedelta(minutes=self._WINDOW_MINUTES)

            # Candles BEFORE this window (no lookahead)
            pre_candles = [c for c in candles if c.timestamp < window_start]
            buffer.seed(pre_candles)

            if not buffer.is_ready(self._cfg.strategy.min_candles_required):
                continue

            features = self._extractor.extract(buffer)
            if features is None:
                continue

            result = self._engine.decide(features)
            open_price = window_candles[0].open if window_candles else features.current_price
            close_price = window_candles[-1].close if window_candles else open_price
            stake = self._risk.compute_stake(result.decision)

            is_correct: Optional[bool]
            pnl: float

            if result.decision == Decision.NO_TRADE or stake == 0.0:
                is_correct = None
                pnl = 0.0
            else:
                actual_up = close_price >= open_price
                predicted_up = result.decision == Decision.UP
                is_correct = actual_up == predicted_up
                pnl = self._risk.compute_pnl(stake, is_correct)

            self._risk.record_result(pnl, is_correct)

            trade_counter += 1
            from app.simulation.paper_trade import OpenTrade, resolve_trade as _resolve
            open_trade = OpenTrade(
                trade_id=trade_counter,
                window_start=window_start,
                window_end=w_end,
                open_price=open_price,
                decision=result.decision,
                confidence=result.confidence,
                regime=result.regime,
                signal_scores=result.signal_scores,
                reason=result.reason,
                stake=stake,
                opened_at=window_start,
            )
            record = _resolve(
                open_trade=open_trade,
                close_price=close_price,
                balance_after=self._risk.balance,
                pnl=pnl,
                is_correct=is_correct,
            )
            records.append(record)

        self._reporter.save_records(records)
        self._reporter.print_summary(records)
        logger.info("Backtest complete. Final balance: %.2f", self._risk.balance)
        return records

    def _group_into_windows(
        self, candles: List[Candle]
    ) -> List[tuple[datetime, List[Candle]]]:
        """Group 1-minute candles into (window_start, [candles]) pairs."""
        windows: dict[datetime, List[Candle]] = {}
        for c in candles:
            ws = floor_to_window(c.timestamp, self._WINDOW_MINUTES)
            windows.setdefault(ws, []).append(c)
        return sorted(windows.items())
