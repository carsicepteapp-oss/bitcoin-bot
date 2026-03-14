"""Feature extractor — translates a CandleBuffer into a FeatureSet."""
from __future__ import annotations

import logging
from typing import Optional

from app.config import FeatureConfig
from app.data.buffer import CandleBuffer
from app.features import indicators as ind
from app.models.signal import FeatureSet
from app.utils.math_utils import safe_div

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """Computes all features from a CandleBuffer snapshot."""

    def __init__(self, cfg: FeatureConfig) -> None:
        self._cfg = cfg

    def extract(self, buffer: CandleBuffer) -> Optional[FeatureSet]:
        """Extract features from *buffer*.

        Returns None when the buffer does not have enough candles.
        """
        min_required = max(
            self._cfg.ema_long,
            self._cfg.rsi_period + 1,
            self._cfg.atr_period + 1,
            self._cfg.zscore_lookback,
            self._cfg.volatility_lookback + 1,
        )

        if not buffer.is_ready(min_required):
            logger.debug(
                "Buffer not ready: %d/%d candles", buffer.size, min_required
            )
            return None

        candles = buffer.all_candles()
        closes = [c.close for c in candles]
        opens = [c.open for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        volumes = [c.volume for c in candles]
        price = closes[-1]

        cfg = self._cfg

        # ── EMAs ─────────────────────────────────────────────────────────────
        e5 = ind.ema(closes, cfg.ema_short) or price
        e9 = ind.ema(closes, cfg.ema_mid) or price
        e20 = ind.ema(closes, cfg.ema_long) or price

        ema_cross_short = safe_div(e5 - e9, price)
        ema_cross_long = safe_div(e9 - e20, price)

        # ── RSI ───────────────────────────────────────────────────────────────
        rsi_val = ind.rsi(closes, cfg.rsi_period) or 50.0

        # ── ATR ───────────────────────────────────────────────────────────────
        atr_val = ind.atr(highs, lows, closes, cfg.atr_period) or 0.0
        last_range = highs[-1] - lows[-1]
        atr_ratio = safe_div(last_range, atr_val) if atr_val > 0 else 1.0

        # ── Returns ───────────────────────────────────────────────────────────
        r1 = ind.period_return(closes, 1)
        r3 = ind.period_return(closes, 3)
        r5 = ind.period_return(closes, 5)
        r10 = ind.period_return(closes, 10)
        r15 = ind.period_return(closes, 15)

        # ── Momentum ──────────────────────────────────────────────────────────
        mom = ind.momentum(closes, cfg.momentum_period)

        # ── Volatility ────────────────────────────────────────────────────────
        vol_short = ind.volatility(closes, cfg.vol_short_window) or 0.0
        vol_long = ind.volatility(closes, cfg.volatility_lookback) or vol_short
        vol_ratio = safe_div(vol_short, vol_long) if vol_long > 0 else 1.0

        # ── Z-score ───────────────────────────────────────────────────────────
        z = ind.zscore(closes, cfg.zscore_lookback) or 0.0

        # ── Candle sequence ───────────────────────────────────────────────────
        seq_score = ind.candle_sequence_score(opens, closes, cfg.candle_sequence_lookback)

        # ── Range expansion ───────────────────────────────────────────────────
        range_exp = ind.range_expansion(highs, lows)

        # ── Price vs MA ───────────────────────────────────────────────────────
        price_vs_e5 = safe_div(price - e5, price)
        price_vs_e20 = safe_div(price - e20, price)

        # ── Volume ────────────────────────────────────────────────────────────
        vol_spike = ind.volume_spike(volumes)
        vol_trend = ind.volume_trend(volumes)

        # ── Composite scores ──────────────────────────────────────────────────
        micro = ind.micro_trend_score(closes)
        noise = ind.noise_score(opens, closes, highs, lows, cfg.candle_sequence_lookback)
        trend_str = ind.trend_strength_score(closes)

        # ── MACD ─────────────────────────────────────────────────────────────
        macd_result = ind.macd(closes, fast=12, slow=26, signal_period=9)
        if macd_result:
            macd_line_val, macd_sig_val, macd_hist_val = macd_result
            macd_result_prev = ind.macd(closes[:-1], fast=12, slow=26, signal_period=9)
            macd_hist_slope = (macd_hist_val - macd_result_prev[2]) if macd_result_prev else 0.0
        else:
            macd_line_val = macd_sig_val = macd_hist_val = macd_hist_slope = 0.0

        # ── Bollinger Bands ───────────────────────────────────────────────────
        bb_pct_b = ind.bollinger_percent_b(closes, period=20) or 0.5
        bb_bw = ind.bollinger_bandwidth(closes, period=20) or 0.02

        # ── Stochastic RSI ────────────────────────────────────────────────────
        stoch_k = ind.stoch_rsi(closes, rsi_period=14, stoch_period=14) or 0.5

        # ── Higher timeframe trend ─────────────────────────────────────────────
        e50 = ind.ema(closes, 50) or price
        ema50_sl = ind.ema_slope(closes, period=50, lookback=3)
        ema_cross_50 = safe_div(e20 - e50, price)

        # ── Support / Resistance ──────────────────────────────────────────────
        dist_res, dist_sup = ind.nearest_sr_distance(closes, highs, lows, lookback=30)

        return FeatureSet(
            return_1m=r1,
            return_3m=r3,
            return_5m=r5,
            return_10m=r10,
            return_15m=r15,
            ema5=e5,
            ema9=e9,
            ema20=e20,
            ema_cross_short=ema_cross_short,
            ema_cross_long=ema_cross_long,
            rsi=rsi_val,
            atr=atr_val,
            atr_ratio=atr_ratio,
            momentum=mom,
            volatility=vol_short,
            volatility_ratio=vol_ratio,
            candle_sequence_score=seq_score,
            range_expansion=range_exp,
            price_vs_ema5=price_vs_e5,
            price_vs_ema20=price_vs_e20,
            zscore=z,
            volume_spike=vol_spike,
            volume_trend=vol_trend,
            micro_trend_score=micro,
            noise_score=noise,
            trend_strength_score=trend_str,
            macd_line=macd_line_val,
            macd_signal=macd_sig_val,
            macd_histogram=macd_hist_val,
            macd_histogram_slope=macd_hist_slope,
            bb_percent_b=bb_pct_b,
            bb_bandwidth=bb_bw,
            stoch_rsi_k=stoch_k,
            ema50_slope=ema50_sl,
            ema_cross_50=ema_cross_50,
            dist_to_resistance=dist_res,
            dist_to_support=dist_sup,
            current_price=price,
        )
