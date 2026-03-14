"""Application configuration — loaded from environment variables via .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from project root (one level above this file)
_ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _str(key: str, default: str) -> str:
    return os.getenv(key, default)


def _int(key: str, default: int) -> int:
    val = os.getenv(key)
    return int(val) if val is not None else default


def _float(key: str, default: float) -> float:
    val = os.getenv(key)
    return float(val) if val is not None else default


def _bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes")


# ── Sub-configs ───────────────────────────────────────────────────────────────

@dataclass
class DataConfig:
    """Data source and polling settings."""

    source: str = field(default_factory=lambda: _str("DATA_SOURCE", "binance"))
    symbol: str = field(default_factory=lambda: _str("SYMBOL", "BTCUSDT"))
    candle_interval: str = field(default_factory=lambda: _str("CANDLE_INTERVAL", "1m"))
    polling_interval_sec: int = field(default_factory=lambda: _int("POLLING_INTERVAL_SEC", 15))
    buffer_size: int = field(default_factory=lambda: _int("BUFFER_SIZE", 200))
    request_timeout_sec: int = field(default_factory=lambda: _int("REQUEST_TIMEOUT_SEC", 10))


@dataclass
class FeatureConfig:
    """Feature engineering window lengths."""

    ema_short: int = field(default_factory=lambda: _int("EMA_SHORT", 5))
    ema_mid: int = field(default_factory=lambda: _int("EMA_MID", 9))
    ema_long: int = field(default_factory=lambda: _int("EMA_LONG", 20))
    rsi_period: int = field(default_factory=lambda: _int("RSI_PERIOD", 14))
    atr_period: int = field(default_factory=lambda: _int("ATR_PERIOD", 14))
    momentum_period: int = field(default_factory=lambda: _int("MOMENTUM_PERIOD", 5))
    zscore_lookback: int = field(default_factory=lambda: _int("ZSCORE_LOOKBACK", 20))
    volatility_lookback: int = field(default_factory=lambda: _int("VOLATILITY_LOOKBACK", 20))
    vol_short_window: int = field(default_factory=lambda: _int("VOL_SHORT_WINDOW", 5))
    candle_sequence_lookback: int = field(
        default_factory=lambda: _int("CANDLE_SEQUENCE_LOOKBACK", 5)
    )


@dataclass
class StrategyConfig:
    """Decision engine thresholds."""

    confidence_threshold: float = field(
        default_factory=lambda: _float("CONFIDENCE_THRESHOLD", 55.0)
    )
    sideways_confidence_penalty: float = field(
        default_factory=lambda: _float("SIDEWAYS_CONFIDENCE_PENALTY", 10.0)
    )
    high_vol_confidence_penalty: float = field(
        default_factory=lambda: _float("HIGH_VOL_CONFIDENCE_PENALTY", 15.0)
    )
    chaotic_confidence_penalty: float = field(
        default_factory=lambda: _float("CHAOTIC_CONFIDENCE_PENALTY", 20.0)
    )
    min_candles_required: int = field(
        default_factory=lambda: _int("MIN_CANDLES_REQUIRED", 25)
    )
    always_trade: bool = field(
        default_factory=lambda: _bool("ALWAYS_TRADE", False)
    )


@dataclass
class RiskConfig:
    """Risk and money-management parameters."""

    initial_balance: float = field(default_factory=lambda: _float("INITIAL_BALANCE", 1000.0))
    stake_mode: str = field(default_factory=lambda: _str("STAKE_MODE", "fixed"))
    stake_fixed: float = field(default_factory=lambda: _float("STAKE_FIXED", 10.0))
    stake_percent: float = field(default_factory=lambda: _float("STAKE_PERCENT", 1.0))
    max_daily_loss: float = field(default_factory=lambda: _float("MAX_DAILY_LOSS", 50.0))
    max_consecutive_losses: int = field(
        default_factory=lambda: _int("MAX_CONSECUTIVE_LOSSES", 3)
    )
    cooldown_windows: int = field(default_factory=lambda: _int("COOLDOWN_WINDOWS", 2))
    loss_reduction_factor: float = field(
        default_factory=lambda: _float("LOSS_REDUCTION_FACTOR", 0.5)
    )
    slippage_pct: float = field(default_factory=lambda: _float("SLIPPAGE_PCT", 0.0))


@dataclass
class VolatilityFilterConfig:
    """Volatility-based no-trade filters."""

    atr_ratio_max: float = field(default_factory=lambda: _float("ATR_RATIO_MAX", 2.5))
    noise_score_max: float = field(default_factory=lambda: _float("NOISE_SCORE_MAX", 0.7))
    vol_ratio_max: float = field(default_factory=lambda: _float("VOL_RATIO_MAX", 3.0))


@dataclass
class OutputConfig:
    """Logging and report paths."""

    log_level: str = field(default_factory=lambda: _str("LOG_LEVEL", "INFO"))
    log_dir: Path = field(default_factory=lambda: Path(_str("LOG_DIR", "logs")))
    reports_dir: Path = field(default_factory=lambda: Path(_str("REPORTS_DIR", "reports")))
    data_dir: Path = field(default_factory=lambda: Path(_str("DATA_DIR", "data")))


@dataclass
class PolymarketConfig:
    """Polymarket real-bet settings (only active when private key is set)."""

    private_key: str = field(default_factory=lambda: _str("POLYMARKET_PRIVATE_KEY", ""))
    stake_pct: float = field(default_factory=lambda: _float("POLYMARKET_STAKE_PCT", 20.0))
    min_stake_usdc: float = field(default_factory=lambda: _float("POLYMARKET_MIN_STAKE", 1.0))
    enabled: bool = field(default_factory=lambda: bool(_str("POLYMARKET_PRIVATE_KEY", "")))


@dataclass
class AppConfig:
    """Root configuration object."""

    data: DataConfig = field(default_factory=DataConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    volatility_filter: VolatilityFilterConfig = field(default_factory=VolatilityFilterConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    polymarket: PolymarketConfig = field(default_factory=PolymarketConfig)

    def ensure_dirs(self) -> None:
        """Create all output directories if they do not exist."""
        for directory in (
            self.output.log_dir,
            self.output.reports_dir,
            self.output.data_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


# ── Singleton ─────────────────────────────────────────────────────────────────

_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Return the singleton AppConfig, constructing it on first call."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
