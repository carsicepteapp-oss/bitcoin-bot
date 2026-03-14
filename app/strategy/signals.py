"""Individual signal functions — each returns a score in [-1.0, +1.0].

Convention:
  +1.0 = strong UP signal
  -1.0 = strong DOWN signal
   0.0 = neutral
"""
from __future__ import annotations

from app.models.signal import FeatureSet
from app.utils.math_utils import clamp, safe_div

# ── Constants ─────────────────────────────────────────────────────────────────
_RSI_OVERSOLD = 30.0
_RSI_OVERBOUGHT = 70.0
_RSI_MIDPOINT = 50.0
_ZSCORE_EXTREME = 2.0
_MOMENTUM_SCALE = 0.005
_RETURN_SCALE = 0.003
_VOLUME_SPIKE_THRESHOLD = 1.5


# ── 1. EMA Crossover ──────────────────────────────────────────────────────────

def ema_crossover_signal(f: FeatureSet) -> float:
    """Score based on EMA alignment (ema5 vs ema9 vs ema20)."""
    short_score = clamp(f.ema_cross_short / 0.001, -1.0, 1.0)
    long_score  = clamp(f.ema_cross_long  / 0.002, -1.0, 1.0)
    return 0.6 * short_score + 0.4 * long_score


# ── 2. RSI ────────────────────────────────────────────────────────────────────

def rsi_signal(f: FeatureSet) -> float:
    """Trend-following RSI bias combined with extreme-level mean-reversion."""
    rsi = f.rsi
    trend_score = clamp((rsi - _RSI_MIDPOINT) / _RSI_MIDPOINT, -1.0, 1.0)

    if rsi >= _RSI_OVERBOUGHT:
        reversion_score = -clamp((rsi - _RSI_OVERBOUGHT) / 30.0, 0.0, 1.0)
    elif rsi <= _RSI_OVERSOLD:
        reversion_score = clamp((_RSI_OVERSOLD - rsi) / 30.0, 0.0, 1.0)
    else:
        reversion_score = 0.0

    return clamp(0.5 * trend_score + 0.5 * reversion_score, -1.0, 1.0)


# ── 3. Momentum ───────────────────────────────────────────────────────────────

def momentum_signal(f: FeatureSet) -> float:
    """Score based on recent rate-of-change."""
    return clamp(f.momentum / _MOMENTUM_SCALE, -1.0, 1.0)


# ── 4. Mean Reversion (Z-score) ───────────────────────────────────────────────

def mean_reversion_signal(f: FeatureSet) -> float:
    """High z-score → fade the move (DOWN); low z → UP."""
    return clamp(-f.zscore / _ZSCORE_EXTREME, -1.0, 1.0)


# ── 5. Trend Following ────────────────────────────────────────────────────────

def trend_following_signal(f: FeatureSet) -> float:
    """Score based on multi-period returns and micro trend."""
    r5    = clamp(f.return_5m  / _RETURN_SCALE,        -1.0, 1.0)
    r10   = clamp(f.return_10m / (_RETURN_SCALE * 2),  -1.0, 1.0)
    micro = clamp(f.micro_trend_score,                  -1.0, 1.0)
    return clamp(0.4 * r5 + 0.3 * r10 + 0.3 * micro,   -1.0, 1.0)


# ── 6. Volume Confirmation ────────────────────────────────────────────────────

def volume_signal(f: FeatureSet) -> float:
    """Volume spike amplifies the direction of recent price action."""
    if f.volume_spike < _VOLUME_SPIKE_THRESHOLD:
        return 0.0
    direction = 1.0 if f.return_1m >= 0 else -1.0
    strength = clamp((f.volume_spike - 1.0) / 4.0, 0.0, 1.0)
    return direction * strength


# ── 7. Candle Pattern ─────────────────────────────────────────────────────────

def candle_pattern_signal(f: FeatureSet) -> float:
    """Score based on recent candle direction sequence."""
    return clamp(f.candle_sequence_score, -1.0, 1.0)


# ── 8. Volatility Multiplier ──────────────────────────────────────────────────

def volatility_adjusted_signal(f: FeatureSet) -> float:
    """Returns a weight multiplier [0, 1] based on how choppy the market is."""
    atr_penalty   = clamp(1.0 - (f.atr_ratio   - 1.0) / 3.0, 0.0, 1.0)
    noise_penalty = clamp(1.0 - f.noise_score,                 0.0, 1.0)
    return atr_penalty * noise_penalty


# ── 9. Price vs MA ────────────────────────────────────────────────────────────

def price_vs_ma_signal(f: FeatureSet) -> float:
    """Mean-reversion: price far from EMAs → fade."""
    dist_e20 = clamp(-f.price_vs_ema20 / 0.005, -1.0, 1.0)
    dist_e5  = clamp(-f.price_vs_ema5  / 0.002, -1.0, 1.0)
    return 0.6 * dist_e20 + 0.4 * dist_e5


# ── 10. MACD ─────────────────────────────────────────────────────────────────

def macd_signal(f: FeatureSet) -> float:
    """MACD histogram direction + slope + crossover.

    Histogram > 0 and rising = strong UP. Histogram < 0 and falling = strong DOWN.
    """
    price = f.current_price if f.current_price > 0 else 1.0

    hist_score  = clamp(f.macd_histogram       / (price * 0.001),  -1.0, 1.0)
    slope_score = clamp(f.macd_histogram_slope / (price * 0.0005), -1.0, 1.0)
    cross       = f.macd_line - f.macd_signal
    cross_score = clamp(cross / (price * 0.0008), -1.0, 1.0)

    return clamp(0.4 * hist_score + 0.35 * slope_score + 0.25 * cross_score, -1.0, 1.0)


# ── 11. Bollinger Bands ───────────────────────────────────────────────────────

def bollinger_signal(f: FeatureSet) -> float:
    """Bollinger %B mean-reversion.

    Above upper band → overbought (DOWN). Below lower band → oversold (UP).
    """
    pct_b = f.bb_percent_b
    if pct_b > 1.0:
        return clamp(-(pct_b - 1.0) * 3.0 - 0.5, -1.0, 1.0)
    elif pct_b < 0.0:
        return clamp((-pct_b) * 3.0 + 0.5, -1.0, 1.0)
    else:
        return clamp((0.5 - pct_b) * 0.8, -1.0, 1.0)


# ── 12. Stochastic RSI ────────────────────────────────────────────────────────

def stoch_rsi_signal(f: FeatureSet) -> float:
    """StochRSI — more sensitive than RSI for short timeframes.

    >0.8 = overbought (DOWN), <0.2 = oversold (UP).
    """
    k = f.stoch_rsi_k
    if k >= 0.8:
        return clamp(-(k - 0.8) / 0.2 - 0.3, -1.0, 1.0)
    elif k <= 0.2:
        return clamp((0.2 - k) / 0.2 + 0.3, -1.0, 1.0)
    else:
        return clamp((k - 0.5) * 0.6, -1.0, 1.0)


# ── 13. Higher Timeframe Trend ────────────────────────────────────────────────

def higher_tf_trend_signal(f: FeatureSet) -> float:
    """EMA(50) slope + EMA20 vs EMA50 alignment.

    Identifies macro trend direction to filter counter-trend noise.
    """
    slope_score = clamp(f.ema50_slope  / 0.0003, -1.0, 1.0)
    cross_score = clamp(f.ema_cross_50 / 0.003,  -1.0, 1.0)
    return clamp(0.5 * slope_score + 0.5 * cross_score, -1.0, 1.0)


# ── 14. Support / Resistance ──────────────────────────────────────────────────

def support_resistance_signal(f: FeatureSet) -> float:
    """Near resistance → lean DOWN; near support → lean UP."""
    if f.dist_to_resistance < 0.003:
        return clamp(-(0.003 - f.dist_to_resistance) / 0.003, -1.0, 0.0)
    if f.dist_to_support < 0.003:
        return clamp((0.003 - f.dist_to_support) / 0.003, 0.0, 1.0)
    return 0.0
