"""Unit tests for technical indicators."""
import math
import pytest

from app.features.indicators import (
    ema,
    rsi,
    atr,
    period_return,
    volatility,
    momentum,
    zscore,
    candle_sequence_score,
    range_expansion,
    volume_spike,
    micro_trend_score,
    noise_score,
    trend_strength_score,
)


class TestEma:
    def test_returns_none_when_insufficient_data(self):
        assert ema([1.0, 2.0], period=5) is None

    def test_single_period_returns_last_value(self):
        result = ema([10.0, 20.0, 30.0], period=1)
        assert result == pytest.approx(30.0, rel=1e-6)

    def test_ema_with_flat_prices(self):
        prices = [100.0] * 20
        result = ema(prices, period=9)
        assert result == pytest.approx(100.0, rel=1e-4)

    def test_ema_follows_trend(self):
        # Rising prices — EMA should be below last price (lagging)
        prices = list(range(1, 30))
        result = ema(prices, period=9)
        assert result is not None
        assert result < prices[-1]


class TestRsi:
    def test_returns_none_when_insufficient_data(self):
        assert rsi([1.0] * 10, period=14) is None

    def test_all_gains_returns_100(self):
        prices = [float(i) for i in range(1, 20)]
        result = rsi(prices, period=14)
        assert result == pytest.approx(100.0, abs=1.0)

    def test_all_losses_returns_0(self):
        prices = [float(20 - i) for i in range(19)]
        result = rsi(prices, period=14)
        assert result == pytest.approx(0.0, abs=1.0)

    def test_rsi_in_range(self):
        import random
        random.seed(42)
        prices = [100.0 + random.gauss(0, 1) for _ in range(50)]
        result = rsi(prices, period=14)
        assert result is not None
        assert 0.0 <= result <= 100.0


class TestAtr:
    def test_returns_none_when_insufficient_data(self):
        assert atr([1.0] * 5, [1.0] * 5, [1.0] * 5, period=14) is None

    def test_constant_range_equals_range_size(self):
        n = 20
        highs = [110.0] * n
        lows = [90.0] * n
        closes = [100.0] * n
        result = atr(highs, lows, closes, period=14)
        assert result == pytest.approx(20.0, rel=1e-4)

    def test_atr_positive(self):
        import random
        random.seed(0)
        closes = [100.0 + random.gauss(0, 2) for _ in range(30)]
        highs = [c + abs(random.gauss(0, 1)) for c in closes]
        lows = [c - abs(random.gauss(0, 1)) for c in closes]
        result = atr(highs, lows, closes, period=14)
        assert result is not None
        assert result > 0


class TestReturns:
    def test_zero_return_for_same_price(self):
        prices = [100.0] * 10
        assert period_return(prices, 5) == pytest.approx(0.0)

    def test_positive_return(self):
        prices = [100.0] * 9 + [110.0]
        assert period_return(prices, 5) == pytest.approx(0.1, rel=1e-4)

    def test_insufficient_data_returns_zero(self):
        assert period_return([1.0, 2.0], lookback=5) == 0.0


class TestZscore:
    def test_returns_none_when_insufficient(self):
        assert zscore([1.0] * 5, window=20) is None

    def test_zero_zscore_for_mean_price(self):
        prices = [100.0] * 20
        result = zscore(prices, window=20)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_positive_zscore_for_high_price(self):
        prices = [100.0] * 19 + [200.0]
        result = zscore(prices, window=20)
        assert result is not None
        assert result > 0


class TestCandleSequenceScore:
    def test_all_bullish(self):
        opens = [100.0] * 5
        closes = [110.0] * 5
        assert candle_sequence_score(opens, closes, 5) == pytest.approx(1.0)

    def test_all_bearish(self):
        opens = [110.0] * 5
        closes = [100.0] * 5
        assert candle_sequence_score(opens, closes, 5) == pytest.approx(-1.0)

    def test_mixed(self):
        opens = [100.0, 110.0, 100.0, 110.0, 100.0]
        closes = [110.0, 100.0, 110.0, 100.0, 110.0]
        score = candle_sequence_score(opens, closes, 5)
        assert score == pytest.approx(0.2)


class TestTrendStrength:
    def test_perfectly_trending_is_one(self):
        prices = [float(i) for i in range(1, 11)]
        assert trend_strength_score(prices, window=10) == pytest.approx(1.0)

    def test_choppy_is_low(self):
        prices = [100.0, 110.0, 90.0, 110.0, 90.0, 110.0, 90.0, 110.0, 90.0, 100.0]
        score = trend_strength_score(prices, window=10)
        assert score < 0.3
