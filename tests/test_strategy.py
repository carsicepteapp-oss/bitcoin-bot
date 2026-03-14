"""Unit tests for signal functions and ensemble engine."""
import pytest

from app.models.signal import Decision, FeatureSet, MarketRegime
from app.strategy import signals as sig
from app.config import StrategyConfig, VolatilityFilterConfig
from app.regime.detector import RegimeDetector
from app.strategy.ensemble import EnsembleDecisionEngine


def _neutral_features(**overrides) -> FeatureSet:
    defaults = dict(
        return_1m=0.0, return_3m=0.0, return_5m=0.0, return_10m=0.0, return_15m=0.0,
        ema5=100.0, ema9=100.0, ema20=100.0, ema_cross_short=0.0, ema_cross_long=0.0,
        rsi=50.0, atr=1.0, atr_ratio=1.0, momentum=0.0,
        volatility=0.001, volatility_ratio=1.0, candle_sequence_score=0.0,
        range_expansion=1.0, price_vs_ema5=0.0, price_vs_ema20=0.0, zscore=0.0,
        volume_spike=1.0, volume_trend=0.0, micro_trend_score=0.0,
        noise_score=0.2, trend_strength_score=0.5, current_price=100.0,
    )
    defaults.update(overrides)
    return FeatureSet(**defaults)


class TestSignals:
    def test_ema_crossover_neutral_at_zero(self):
        f = _neutral_features()
        assert sig.ema_crossover_signal(f) == pytest.approx(0.0)

    def test_ema_crossover_bullish(self):
        f = _neutral_features(ema_cross_short=0.002, ema_cross_long=0.003)
        assert sig.ema_crossover_signal(f) > 0

    def test_rsi_neutral_at_50(self):
        f = _neutral_features(rsi=50.0)
        assert sig.rsi_signal(f) == pytest.approx(0.0, abs=0.01)

    def test_rsi_overbought_bearish(self):
        f = _neutral_features(rsi=80.0)
        assert sig.rsi_signal(f) < 0

    def test_rsi_oversold_bullish(self):
        f = _neutral_features(rsi=20.0)
        assert sig.rsi_signal(f) > 0

    def test_momentum_signal_positive(self):
        f = _neutral_features(momentum=0.01)
        assert sig.momentum_signal(f) > 0

    def test_mean_reversion_positive_zscore_gives_down(self):
        f = _neutral_features(zscore=2.0)
        assert sig.mean_reversion_signal(f) < 0

    def test_volume_signal_no_spike(self):
        f = _neutral_features(volume_spike=1.0)
        assert sig.volume_signal(f) == pytest.approx(0.0)

    def test_all_signals_in_range(self):
        f = _neutral_features(rsi=65.0, momentum=0.005, zscore=1.5, volume_spike=2.0, return_1m=0.002)
        for fn in [
            sig.ema_crossover_signal, sig.rsi_signal, sig.momentum_signal,
            sig.mean_reversion_signal, sig.trend_following_signal, sig.volume_signal,
            sig.candle_pattern_signal, sig.price_vs_ma_signal,
        ]:
            result = fn(f)
            assert -1.0 <= result <= 1.0, f"{fn.__name__} out of range: {result}"


class TestEnsembleEngine:
    def setup_method(self):
        self.engine = EnsembleDecisionEngine(
            strategy_cfg=StrategyConfig(),
            vol_filter_cfg=VolatilityFilterConfig(),
            regime_detector=RegimeDetector(),
        )

    def test_returns_signal_result(self):
        from app.models.signal import SignalResult
        f = _neutral_features()
        result = self.engine.decide(f)
        assert isinstance(result, SignalResult)

    def test_decision_is_valid_enum(self):
        f = _neutral_features()
        result = self.engine.decide(f)
        assert result.decision in Decision

    def test_confidence_in_range(self):
        f = _neutral_features()
        result = self.engine.decide(f)
        assert 0.0 <= result.confidence <= 100.0

    def test_extreme_noise_forces_no_trade(self):
        f = _neutral_features(noise_score=0.9, atr_ratio=0.5)
        result = self.engine.decide(f)
        # noise_score > noise_score_max (0.7) → NO_TRADE
        assert result.decision == Decision.NO_TRADE

    def test_strong_bull_signal_gives_up(self):
        f = _neutral_features(
            ema_cross_short=0.005, ema_cross_long=0.008,
            rsi=60.0, momentum=0.015, return_5m=0.01,
            micro_trend_score=0.9, trend_strength_score=0.8,
            candle_sequence_score=0.8, noise_score=0.1,
        )
        result = self.engine.decide(f)
        # With strong bull signals, decision should be UP or NO_TRADE (if conf < threshold)
        assert result.decision in (Decision.UP, Decision.NO_TRADE)
