"""Signal and decision data models."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict


class Decision(str, Enum):
    """Trading decision for a 5-minute window."""

    UP = "UP"
    DOWN = "DOWN"
    NO_TRADE = "NO_TRADE"


class MarketRegime(str, Enum):
    """Classified market regime."""

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    CHAOTIC = "CHAOTIC"


@dataclass
class FeatureSet:
    """All computed features for a given prediction window."""

    # ── Returns ──────────────────────────────────────────────────────────────
    return_1m: float = 0.0
    return_3m: float = 0.0
    return_5m: float = 0.0
    return_10m: float = 0.0
    return_15m: float = 0.0

    # ── Exponential Moving Averages ───────────────────────────────────────────
    ema5: float = 0.0
    ema9: float = 0.0
    ema20: float = 0.0
    ema_cross_short: float = 0.0   # (ema5 - ema9) / price
    ema_cross_long: float = 0.0    # (ema9 - ema20) / price

    # ── RSI ───────────────────────────────────────────────────────────────────
    rsi: float = 50.0

    # ── ATR ───────────────────────────────────────────────────────────────────
    atr: float = 0.0
    atr_ratio: float = 0.0    # last candle range / ATR

    # ── Momentum ─────────────────────────────────────────────────────────────
    momentum: float = 0.0         # rate of change over last N candles

    # ── Volatility ───────────────────────────────────────────────────────────
    volatility: float = 0.0       # std of recent returns
    volatility_ratio: float = 1.0  # current vol / longer-term vol

    # ── Candle sequence ───────────────────────────────────────────────────────
    candle_sequence_score: float = 0.0  # +1 all bullish, -1 all bearish

    # ── Range expansion / compression ────────────────────────────────────────
    range_expansion: float = 0.0  # last range / avg range

    # ── Price distance from MA ────────────────────────────────────────────────
    price_vs_ema5: float = 0.0    # (price - ema5) / price
    price_vs_ema20: float = 0.0   # (price - ema20) / price

    # ── Mean-reversion Z-score ───────────────────────────────────────────────
    zscore: float = 0.0

    # ── Volume ───────────────────────────────────────────────────────────────
    volume_spike: float = 1.0     # last vol / avg vol
    volume_trend: float = 0.0     # slope of volume over recent bars

    # ── Composite scores ─────────────────────────────────────────────────────
    micro_trend_score: float = 0.0
    noise_score: float = 0.0
    trend_strength_score: float = 0.0

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    macd_histogram_slope: float = 0.0

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_percent_b: float = 0.5
    bb_bandwidth: float = 0.02

    # ── Stochastic RSI ────────────────────────────────────────────────────────
    stoch_rsi_k: float = 0.5

    # ── Higher timeframe trend ────────────────────────────────────────────────
    ema50_slope: float = 0.0
    ema_cross_50: float = 0.0

    # ── Support / Resistance ──────────────────────────────────────────────────
    dist_to_resistance: float = 0.0
    dist_to_support: float = 0.0

    # ── Current price ─────────────────────────────────────────────────────────
    current_price: float = 0.0


@dataclass
class SignalResult:
    """Output of the decision engine for a single window."""

    decision: Decision
    confidence: float                          # 0-100
    regime: MarketRegime
    signal_scores: Dict[str, float] = field(default_factory=dict)
    reason: str = ""
    features: FeatureSet = field(default_factory=FeatureSet)
    timestamp: datetime = field(default_factory=datetime.utcnow)
