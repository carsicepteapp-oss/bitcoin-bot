"""Ensemble decision engine — combines individual signals into a final decision."""
from __future__ import annotations

import logging
from typing import Dict, Tuple

from app.config import StrategyConfig, VolatilityFilterConfig
from app.models.signal import Decision, FeatureSet, MarketRegime, SignalResult
from app.regime.detector import RegimeDetector
from app.strategy import signals as sig
from app.utils.math_utils import clamp, normalize_score, weighted_average

logger = logging.getLogger(__name__)

# ── Signal registry ────────────────────────────────────────────────────────────
_SIGNAL_REGISTRY: Dict[str, object] = {
    "ema_crossover":   sig.ema_crossover_signal,
    "rsi":             sig.rsi_signal,
    "momentum":        sig.momentum_signal,
    "mean_reversion":  sig.mean_reversion_signal,
    "trend_following": sig.trend_following_signal,
    "volume":          sig.volume_signal,
    "candle_pattern":  sig.candle_pattern_signal,
    "price_vs_ma":     sig.price_vs_ma_signal,
    "macd":            sig.macd_signal,
    "bollinger":       sig.bollinger_signal,
    "stoch_rsi":       sig.stoch_rsi_signal,
    "higher_tf_trend": sig.higher_tf_trend_signal,
    "support_resist":  sig.support_resistance_signal,
}

_SIGNAL_TO_GROUP: Dict[str, str] = {
    "ema_crossover":   "trend_following",
    "rsi":             "mean_reversion",
    "momentum":        "momentum",
    "mean_reversion":  "mean_reversion",
    "trend_following": "trend_following",
    "volume":          "volume",
    "candle_pattern":  "candle_pattern",
    "price_vs_ma":     "mean_reversion",
    "macd":            "trend_following",
    "bollinger":       "mean_reversion",
    "stoch_rsi":       "mean_reversion",
    "higher_tf_trend": "trend_following",
    "support_resist":  "mean_reversion",
}

_REGIME_PENALTIES: Dict[MarketRegime, float] = {
    MarketRegime.TREND_UP:        0.0,
    MarketRegime.TREND_DOWN:      0.0,
    MarketRegime.SIDEWAYS:        12.0,
    MarketRegime.HIGH_VOLATILITY: 18.0,
    MarketRegime.LOW_VOLATILITY:  5.0,
    MarketRegime.CHAOTIC:         25.0,
}

_MIN_AGREEMENT_RATIO = 0.55     # at least 55% of active signals must agree
_SIGNAL_ACTIVE_THRESHOLD = 0.08  # |score| > this → counts as active signal


class EnsembleDecisionEngine:
    """Combines all signals with regime-adjusted weights and agreement filtering."""

    def __init__(
        self,
        strategy_cfg: StrategyConfig,
        vol_filter_cfg: VolatilityFilterConfig,
        regime_detector: RegimeDetector,
    ) -> None:
        self._strategy_cfg = strategy_cfg
        self._vol_filter_cfg = vol_filter_cfg
        self._regime_detector = regime_detector

    def decide(self, features: FeatureSet) -> SignalResult:
        """Run all signals and return a SignalResult."""
        regime = self._regime_detector.detect(features)
        regime_weights = self._regime_detector.get_weights(regime)

        vol_multiplier = sig.volatility_adjusted_signal(features)

        # ── Compute individual signal scores ──────────────────────────────────
        raw_scores: Dict[str, float] = {}
        for name, fn in _SIGNAL_REGISTRY.items():
            try:
                raw_scores[name] = float(fn(features))  # type: ignore[operator]
            except Exception as exc:
                logger.warning("Signal '%s' raised an error: %s", name, exc)
                raw_scores[name] = 0.0

        # ── Weighted aggregation ───────────────────────────────────────────────
        signal_values = []
        signal_weights = []
        for name, score in raw_scores.items():
            group = _SIGNAL_TO_GROUP.get(name, "trend_following")
            weight = regime_weights.get(group, 1.0) * vol_multiplier
            signal_values.append(score)
            signal_weights.append(weight)

        aggregate = weighted_average(signal_values, signal_weights)

        # ── Signal agreement ───────────────────────────────────────────────────
        agreement_ratio, active_count = self._compute_agreement(raw_scores, aggregate)

        # ── Confidence: blend magnitude + agreement ────────────────────────────
        magnitude_score = normalize_score(abs(aggregate), 0.0, 1.0, 0.0, 100.0)
        agreement_score = agreement_ratio * 100.0
        raw_confidence  = 0.50 * magnitude_score + 0.50 * agreement_score

        penalty    = _REGIME_PENALTIES.get(regime, 0.0)
        confidence = clamp(raw_confidence - penalty, 0.0, 100.0)

        # ── Hard filters ───────────────────────────────────────────────────────
        forced_no_trade = self._apply_hard_filters(features, confidence)

        # ── Insufficient agreement → NO_TRADE ─────────────────────────────────
        if not forced_no_trade and active_count >= 4 and agreement_ratio < _MIN_AGREEMENT_RATIO:
            forced_no_trade = True
            logger.debug(
                "NO_TRADE: agreement %.0f%% < %.0f%% (%d signals)",
                agreement_ratio * 100, _MIN_AGREEMENT_RATIO * 100, active_count,
            )

        # ── Final decision ─────────────────────────────────────────────────────
        always_trade = self._strategy_cfg.always_trade
        threshold    = self._strategy_cfg.confidence_threshold

        if forced_no_trade:
            decision = Decision.NO_TRADE
        elif always_trade or confidence >= threshold:
            decision = Decision.UP if aggregate >= 0 else Decision.DOWN
        else:
            decision = Decision.NO_TRADE

        reason = self._build_reason(
            decision, confidence, regime, aggregate,
            agreement_ratio, active_count, raw_scores, forced_no_trade,
        )

        logger.info(
            "Decision=%s | confidence=%.1f | regime=%s | aggregate=%.3f | reason=%s",
            decision.value, confidence, regime.value, aggregate, reason,
        )

        return SignalResult(
            decision=decision,
            confidence=confidence,
            regime=regime,
            signal_scores=raw_scores,
            reason=reason,
            features=features,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _compute_agreement(
        self, scores: Dict[str, float], aggregate: float
    ) -> Tuple[float, int]:
        """(agreement_ratio, active_count): fraction of active signals agreeing."""
        direction = 1 if aggregate >= 0 else -1
        active = [s for s in scores.values() if abs(s) > _SIGNAL_ACTIVE_THRESHOLD]
        if not active:
            return 0.5, 0
        agreeing = sum(1 for s in active if s * direction > 0)
        return agreeing / len(active), len(active)

    def _apply_hard_filters(self, f: FeatureSet, confidence: float) -> bool:
        vf = self._vol_filter_cfg
        if f.atr_ratio > vf.atr_ratio_max:
            return True
        if f.noise_score > vf.noise_score_max:
            return True
        if f.volatility_ratio > vf.vol_ratio_max:
            return True
        return False

    def _build_reason(
        self,
        decision: Decision,
        confidence: float,
        regime: MarketRegime,
        aggregate: float,
        agreement: float,
        active_count: int,
        scores: Dict[str, float],
        forced: bool,
    ) -> str:
        parts = [f"regime={regime.value}", f"conf={confidence:.1f}"]
        if forced:
            parts.append("forced=NO_TRADE")
        else:
            parts.append(f"agg={aggregate:+.3f}")
            parts.append(f"agree={agreement*100:.0f}%({active_count}sig)")
            top = sorted(scores.items(), key=lambda kv: abs(kv[1]), reverse=True)[:4]
            parts.append("top=[" + " ".join(f"{k}={v:+.2f}" for k, v in top) + "]")
        return " | ".join(parts)
