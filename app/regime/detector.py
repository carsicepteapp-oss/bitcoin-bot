"""Market regime detector."""
from __future__ import annotations

import logging
from typing import Dict

from app.models.signal import FeatureSet, MarketRegime

logger = logging.getLogger(__name__)

# Regime detection thresholds (tuneable)
_TREND_EMA_ALIGN_THRESHOLD = 0.00015  # min ema_cross_long (normalised) to call trend — lowered
_TREND_STRENGTH_MIN = 0.35            # minimum trend_strength_score — lowered from 0.45
_HIGH_VOL_RATIO = 2.2                 # vol_ratio above this → HIGH_VOLATILITY
_LOW_VOL_RATIO = 0.45                 # vol_ratio below this → LOW_VOLATILITY
_CHAOTIC_NOISE = 0.75                 # noise_score above this → CHAOTIC
_CHAOTIC_ATR_RATIO = 3.0              # atr_ratio above this (combined) → CHAOTIC
_SIDEWAYS_RETURN_MAX = 0.0005         # |return_5m| below this → SIDEWAYS candidate — tightened


# ── Weight tables per regime ──────────────────────────────────────────────────
# Each value is a multiplier applied to that signal group's raw score.

REGIME_WEIGHTS: Dict[MarketRegime, Dict[str, float]] = {
    MarketRegime.TREND_UP: {
        "trend_following": 1.5,
        "mean_reversion":  0.3,   # fade mean-reversion in trends
        "momentum":        1.3,
        "volatility":      0.8,
        "volume":          1.2,
        "candle_pattern":  1.0,
    },
    MarketRegime.TREND_DOWN: {
        "trend_following": 1.5,
        "mean_reversion":  0.3,
        "momentum":        1.3,
        "volatility":      0.8,
        "volume":          1.2,
        "candle_pattern":  1.0,
    },
    MarketRegime.SIDEWAYS: {
        "trend_following": 0.4,   # ignore trend signals in sideways
        "mean_reversion":  1.6,   # rely on mean-reversion, bollinger, stochrsi
        "momentum":        0.5,
        "volatility":      0.7,
        "volume":          0.9,
        "candle_pattern":  1.2,
    },
    MarketRegime.HIGH_VOLATILITY: {
        "trend_following": 0.6,
        "mean_reversion":  0.6,
        "momentum":        0.7,
        "volatility":      1.2,
        "volume":          1.3,
        "candle_pattern":  0.5,
    },
    MarketRegime.LOW_VOLATILITY: {
        "trend_following": 0.8,
        "mean_reversion":  1.3,
        "momentum":        0.7,
        "volatility":      0.5,
        "volume":          0.6,
        "candle_pattern":  1.1,
    },
    MarketRegime.CHAOTIC: {
        "trend_following": 0.2,
        "mean_reversion":  0.2,
        "momentum":        0.2,
        "volatility":      0.4,
        "volume":          0.4,
        "candle_pattern":  0.2,
    },
}


class RegimeDetector:
    """Classifies the current market state from a FeatureSet."""

    def detect(self, features: FeatureSet) -> MarketRegime:
        """Return the dominant market regime for the current window."""
        regime = self._classify(features)
        logger.debug(
            "Regime=%s | trend_str=%.2f | noise=%.2f | vol_ratio=%.2f | rsi=%.1f",
            regime.value,
            features.trend_strength_score,
            features.noise_score,
            features.volatility_ratio,
            features.rsi,
        )
        return regime

    def get_weights(self, regime: MarketRegime) -> Dict[str, float]:
        """Return signal group weights for *regime*."""
        return REGIME_WEIGHTS[regime]

    # ── Private ───────────────────────────────────────────────────────────────

    def _classify(self, f: FeatureSet) -> MarketRegime:
        # CHAOTIC takes priority — both extreme noise and range expansion
        if f.noise_score >= _CHAOTIC_NOISE and f.atr_ratio >= _CHAOTIC_ATR_RATIO:
            return MarketRegime.CHAOTIC

        # HIGH_VOLATILITY
        if f.volatility_ratio >= _HIGH_VOL_RATIO:
            return MarketRegime.HIGH_VOLATILITY

        # LOW_VOLATILITY
        if f.volatility_ratio <= _LOW_VOL_RATIO and f.atr_ratio < 0.8:
            return MarketRegime.LOW_VOLATILITY

        # TREND_UP
        if (
            f.ema_cross_long > _TREND_EMA_ALIGN_THRESHOLD
            and f.ema_cross_short > 0
            and f.trend_strength_score >= _TREND_STRENGTH_MIN
            and f.return_5m > 0
        ):
            return MarketRegime.TREND_UP

        # TREND_DOWN
        if (
            f.ema_cross_long < -_TREND_EMA_ALIGN_THRESHOLD
            and f.ema_cross_short < 0
            and f.trend_strength_score >= _TREND_STRENGTH_MIN
            and f.return_5m < 0
        ):
            return MarketRegime.TREND_DOWN

        # SIDEWAYS — low net return and weak trend
        if (
            abs(f.return_5m) <= _SIDEWAYS_RETURN_MAX
            and f.trend_strength_score < _TREND_STRENGTH_MIN
        ):
            return MarketRegime.SIDEWAYS

        # Default: SIDEWAYS if nothing else matched
        return MarketRegime.SIDEWAYS
