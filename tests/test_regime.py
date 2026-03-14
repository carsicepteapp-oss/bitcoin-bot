"""Unit tests for regime detector."""
import pytest

from app.models.signal import FeatureSet, MarketRegime
from app.regime.detector import RegimeDetector


def _base_features(**overrides) -> FeatureSet:
    """Return a default neutral FeatureSet with optional overrides."""
    defaults = dict(
        return_1m=0.0,
        return_3m=0.0,
        return_5m=0.0,
        return_10m=0.0,
        return_15m=0.0,
        ema5=100.0,
        ema9=100.0,
        ema20=100.0,
        ema_cross_short=0.0,
        ema_cross_long=0.0,
        rsi=50.0,
        atr=1.0,
        atr_ratio=1.0,
        momentum=0.0,
        volatility=0.001,
        volatility_ratio=1.0,
        candle_sequence_score=0.0,
        range_expansion=1.0,
        price_vs_ema5=0.0,
        price_vs_ema20=0.0,
        zscore=0.0,
        volume_spike=1.0,
        volume_trend=0.0,
        micro_trend_score=0.0,
        noise_score=0.3,
        trend_strength_score=0.3,
        current_price=100.0,
    )
    defaults.update(overrides)
    return FeatureSet(**defaults)


class TestRegimeDetector:
    def setup_method(self):
        self.detector = RegimeDetector()

    def test_detects_trend_up(self):
        f = _base_features(
            ema_cross_short=0.001,
            ema_cross_long=0.0005,
            trend_strength_score=0.6,
            return_5m=0.002,
        )
        assert self.detector.detect(f) == MarketRegime.TREND_UP

    def test_detects_trend_down(self):
        f = _base_features(
            ema_cross_short=-0.001,
            ema_cross_long=-0.0005,
            trend_strength_score=0.6,
            return_5m=-0.002,
        )
        assert self.detector.detect(f) == MarketRegime.TREND_DOWN

    def test_detects_sideways(self):
        f = _base_features(
            return_5m=0.0001,
            trend_strength_score=0.2,
        )
        assert self.detector.detect(f) == MarketRegime.SIDEWAYS

    def test_detects_high_volatility(self):
        f = _base_features(volatility_ratio=2.5)
        assert self.detector.detect(f) == MarketRegime.HIGH_VOLATILITY

    def test_detects_chaotic(self):
        f = _base_features(noise_score=0.8, atr_ratio=3.0)
        assert self.detector.detect(f) == MarketRegime.CHAOTIC

    def test_returns_weights_for_each_regime(self):
        for regime in MarketRegime:
            weights = self.detector.get_weights(regime)
            assert isinstance(weights, dict)
            assert len(weights) > 0
