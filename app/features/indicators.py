"""Pure-function technical indicators operating on plain Python lists."""
from __future__ import annotations

import math
from typing import List, Optional

from app.utils.math_utils import safe_div, pct_change


# ── EMA ───────────────────────────────────────────────────────────────────────

def ema(prices: List[float], period: int) -> Optional[float]:
    """Exponential moving average of *prices* using standard alpha.

    Returns None when there are fewer values than *period*.
    """
    if len(prices) < period:
        return None
    alpha = 2.0 / (period + 1)
    result = prices[0]
    for price in prices[1:]:
        result = alpha * price + (1.0 - alpha) * result
    return result


def ema_series(prices: List[float], period: int) -> List[Optional[float]]:
    """Return a full EMA series aligned to *prices*."""
    if not prices:
        return []
    alpha = 2.0 / (period + 1)
    results: List[Optional[float]] = [None] * (period - 1)
    current = sum(prices[:period]) / period  # SMA seed
    results.append(current)
    for price in prices[period:]:
        current = alpha * price + (1.0 - alpha) * current
        results.append(current)
    return results


# ── RSI ───────────────────────────────────────────────────────────────────────

def rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Wilder's RSI.

    Returns None when there are fewer than *period + 1* prices.
    """
    if len(prices) < period + 1:
        return None

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    # Initial averages (simple)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder smoothing for remaining
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


# ── ATR ───────────────────────────────────────────────────────────────────────

def true_range(high: float, low: float, prev_close: float) -> float:
    """Single-bar True Range."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14,
) -> Optional[float]:
    """Average True Range using Wilder smoothing.

    Returns None when there are fewer than *period + 1* bars.
    """
    n = len(closes)
    if n < period + 1 or len(highs) != n or len(lows) != n:
        return None

    trs = [
        true_range(highs[i], lows[i], closes[i - 1])
        for i in range(1, n)
    ]

    atr_val = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    return atr_val


# ── Returns ───────────────────────────────────────────────────────────────────

def period_return(prices: List[float], lookback: int) -> float:
    """Return (current - past) / past for the last *lookback* bars.

    Returns 0.0 when not enough data.
    """
    if len(prices) < lookback + 1:
        return 0.0
    return pct_change(prices[-1], prices[-(lookback + 1)])


# ── Volatility ────────────────────────────────────────────────────────────────

def volatility(prices: List[float], window: int) -> Optional[float]:
    """Standard deviation of log returns over *window* bars."""
    if len(prices) < window + 1:
        return None
    log_returns = [
        math.log(prices[i] / prices[i - 1])
        for i in range(len(prices) - window, len(prices))
        if prices[i - 1] > 0 and prices[i] > 0
    ]
    if len(log_returns) < 2:
        return None
    mean = sum(log_returns) / len(log_returns)
    variance = sum((r - mean) ** 2 for r in log_returns) / (len(log_returns) - 1)
    return math.sqrt(variance)


# ── Momentum (Rate of Change) ─────────────────────────────────────────────────

def momentum(prices: List[float], period: int = 5) -> float:
    """Percentage rate of change over *period* bars."""
    return period_return(prices, period)


# ── Z-Score ───────────────────────────────────────────────────────────────────

def zscore(prices: List[float], window: int = 20) -> Optional[float]:
    """Z-score of the last price relative to the rolling window.

    Positive = above mean (potential mean-reversion short).
    Negative = below mean (potential mean-reversion long).
    """
    if len(prices) < window:
        return None
    window_prices = prices[-window:]
    mean = sum(window_prices) / window
    variance = sum((p - mean) ** 2 for p in window_prices) / window
    std = math.sqrt(variance)
    if std == 0.0:
        return 0.0
    return (prices[-1] - mean) / std


# ── Candle sequence score ─────────────────────────────────────────────────────

def candle_sequence_score(opens: List[float], closes: List[float], lookback: int = 5) -> float:
    """Score in [-1, +1] representing recent bullish/bearish bias.

    +1 = all candles bullish, -1 = all bearish.
    """
    n = min(lookback, len(opens), len(closes))
    if n == 0:
        return 0.0
    directions = [
        1.0 if closes[-(n - i)] >= opens[-(n - i)] else -1.0
        for i in range(n)
    ]
    return sum(directions) / n


# ── Range expansion ───────────────────────────────────────────────────────────

def range_expansion(highs: List[float], lows: List[float], lookback: int = 10) -> float:
    """Ratio of last bar range to average range over *lookback* bars.

    > 1 = range expanding, < 1 = compressing.
    """
    if len(highs) < lookback or len(lows) < lookback:
        return 1.0
    ranges = [highs[i] - lows[i] for i in range(-lookback, 0)]
    avg_range = sum(ranges[:-1]) / max(len(ranges) - 1, 1)
    return safe_div(ranges[-1], avg_range, fallback=1.0)


# ── Volume indicators ─────────────────────────────────────────────────────────

def volume_spike(volumes: List[float], lookback: int = 20) -> float:
    """Ratio of latest volume to average volume over *lookback* bars."""
    if len(volumes) < lookback:
        return 1.0
    avg_vol = sum(volumes[-lookback:-1]) / max(lookback - 1, 1)
    return safe_div(volumes[-1], avg_vol, fallback=1.0)


def volume_trend(volumes: List[float], lookback: int = 5) -> float:
    """Normalised linear slope of volume over the last *lookback* bars.

    Positive = growing volume, negative = shrinking.
    Returns value in roughly [-1, 1].
    """
    n = min(lookback, len(volumes))
    if n < 2:
        return 0.0
    vols = volumes[-n:]
    indices = list(range(n))
    mean_x = sum(indices) / n
    mean_y = sum(vols) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(indices, vols))
    den = sum((x - mean_x) ** 2 for x in indices)
    slope = safe_div(num, den, fallback=0.0)
    # Normalise by mean volume so the result is dimensionless
    return safe_div(slope, mean_y if mean_y > 0 else 1.0, fallback=0.0)


# ── Micro-trend score ─────────────────────────────────────────────────────────

def micro_trend_score(closes: List[float], short: int = 3, long: int = 8) -> float:
    """Score in [-1, +1] based on short EMA vs long EMA direction.

    Captures the very recent micro-trend.
    """
    if len(closes) < long:
        return 0.0
    e_short = ema(closes, short)
    e_long = ema(closes, long)
    if e_short is None or e_long is None or closes[-1] == 0:
        return 0.0
    diff_pct = safe_div(e_short - e_long, closes[-1])
    # Normalise: assume a 0.5% deviation is "extreme" → score ±1
    _NORMALISE = 0.005
    return max(-1.0, min(1.0, diff_pct / _NORMALISE))


# ── Noise score ───────────────────────────────────────────────────────────────

def noise_score(
    opens: List[float],
    closes: List[float],
    highs: List[float],
    lows: List[float],
    lookback: int = 5,
) -> float:
    """Score in [0, 1] representing how noisy/choppy recent price action is.

    High noise → consider NO_TRADE.
    Measures ratio of shadow to total range.
    """
    n = min(lookback, len(opens), len(closes), len(highs), len(lows))
    if n == 0:
        return 0.0
    noise_ratios = []
    for i in range(-n, 0):
        total_range = highs[i] - lows[i]
        if total_range == 0:
            noise_ratios.append(1.0)
            continue
        body = abs(closes[i] - opens[i])
        shadow = total_range - body
        noise_ratios.append(safe_div(shadow, total_range))
    return sum(noise_ratios) / len(noise_ratios)


# ── Trend strength ────────────────────────────────────────────────────────────

def trend_strength_score(closes: List[float], window: int = 10) -> float:
    """Score in [0, 1] representing directional consistency.

    Uses the ratio of net move to total path length.
    """
    if len(closes) < window:
        return 0.0
    segment = closes[-window:]
    net_move = abs(segment[-1] - segment[0])
    total_path = sum(abs(segment[i] - segment[i - 1]) for i in range(1, len(segment)))
    return safe_div(net_move, total_path, fallback=0.0)


# ── MACD ──────────────────────────────────────────────────────────────────────

def macd(
    prices: List[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> Optional[tuple[float, float, float]]:
    """MACD indicator: returns (macd_line, signal_line, histogram).

    Returns None when there are not enough data points.
    fast/slow EMA crossover; signal is EMA of MACD line.
    """
    if len(prices) < slow + signal_period:
        return None

    alpha_fast = 2.0 / (fast + 1)
    alpha_slow = 2.0 / (slow + 1)
    alpha_sig  = 2.0 / (signal_period + 1)

    # Seed with SMA
    ema_fast = sum(prices[:fast]) / fast
    ema_slow = sum(prices[:slow]) / slow

    for price in prices[fast:slow]:
        ema_fast = alpha_fast * price + (1 - alpha_fast) * ema_fast

    macd_values: List[float] = []
    for price in prices[slow:]:
        ema_fast = alpha_fast * price + (1 - alpha_fast) * ema_fast
        ema_slow = alpha_slow * price + (1 - alpha_slow) * ema_slow
        macd_values.append(ema_fast - ema_slow)

    if len(macd_values) < signal_period:
        return None

    sig_line = sum(macd_values[:signal_period]) / signal_period
    for val in macd_values[signal_period:]:
        sig_line = alpha_sig * val + (1 - alpha_sig) * sig_line

    macd_line = macd_values[-1]
    histogram  = macd_line - sig_line
    return macd_line, sig_line, histogram


# ── Bollinger Bands ───────────────────────────────────────────────────────────

def bollinger_bands(
    prices: List[float],
    period: int = 20,
    num_std: float = 2.0,
) -> Optional[tuple[float, float, float]]:
    """Bollinger Bands: returns (upper, middle, lower).

    Returns None when there are not enough data points.
    """
    if len(prices) < period:
        return None
    window = prices[-period:]
    middle = sum(window) / period
    variance = sum((p - middle) ** 2 for p in window) / period
    std = math.sqrt(variance)
    return middle + num_std * std, middle, middle - num_std * std


def bollinger_percent_b(prices: List[float], period: int = 20, num_std: float = 2.0) -> Optional[float]:
    """Bollinger %B: position of price within bands (0=lower, 1=upper, >1 above, <0 below)."""
    result = bollinger_bands(prices, period, num_std)
    if result is None:
        return None
    upper, _mid, lower = result
    band_width = upper - lower
    if band_width == 0:
        return 0.5
    return (prices[-1] - lower) / band_width


def bollinger_bandwidth(prices: List[float], period: int = 20, num_std: float = 2.0) -> Optional[float]:
    """Bollinger Bandwidth: (upper - lower) / middle. Measures volatility expansion."""
    result = bollinger_bands(prices, period, num_std)
    if result is None:
        return None
    upper, middle, lower = result
    if middle == 0:
        return None
    return (upper - lower) / middle


# ── Stochastic RSI ────────────────────────────────────────────────────────────

def stoch_rsi(
    prices: List[float],
    rsi_period: int = 14,
    stoch_period: int = 14,
) -> Optional[float]:
    """Stochastic RSI: RSI normalised within its own min/max range.

    Returns a value in [0, 1]. >0.8 = overbought, <0.2 = oversold.
    Returns None when not enough data.
    """
    needed = rsi_period + stoch_period + 1
    if len(prices) < needed:
        return None

    # Compute an RSI series over a rolling window
    rsi_vals: List[float] = []
    for i in range(stoch_period):
        end = len(prices) - stoch_period + i + 1
        start = end - rsi_period - 1
        if start < 0:
            continue
        r = rsi(prices[start:end], rsi_period)
        if r is not None:
            rsi_vals.append(r)

    if len(rsi_vals) < stoch_period:
        return None

    min_rsi = min(rsi_vals)
    max_rsi = max(rsi_vals)
    if max_rsi == min_rsi:
        return 0.5
    return (rsi_vals[-1] - min_rsi) / (max_rsi - min_rsi)


# ── Higher timeframe trend (EMA slope) ───────────────────────────────────────

def ema_slope(prices: List[float], period: int, lookback: int = 3) -> float:
    """Slope of EMA(period) over the last *lookback* bars, normalised by price.

    Positive = rising EMA (bullish), negative = falling (bearish).
    """
    if len(prices) < period + lookback:
        return 0.0

    ema_now  = ema(prices, period)
    ema_prev = ema(prices[:-lookback], period)

    if ema_now is None or ema_prev is None or prices[-1] == 0:
        return 0.0
    return (ema_now - ema_prev) / prices[-1]


# ── Support / Resistance proximity ────────────────────────────────────────────

def nearest_sr_distance(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    lookback: int = 30,
) -> tuple[float, float]:
    """Returns (distance_to_nearest_resistance, distance_to_nearest_support) as fractions.

    Positive = price is below resistance / above support.
    """
    if len(closes) < lookback:
        return 0.0, 0.0

    price = closes[-1]
    recent_highs = highs[-lookback:-1]
    recent_lows  = lows[-lookback:-1]

    resistance = max(recent_highs) if recent_highs else price
    support    = min(recent_lows)  if recent_lows  else price

    dist_res = safe_div(resistance - price, price)
    dist_sup = safe_div(price - support,    price)
    return dist_res, dist_sup
