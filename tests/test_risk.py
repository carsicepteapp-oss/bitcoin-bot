"""Unit tests for the risk manager."""
import pytest

from app.config import RiskConfig
from app.models.signal import Decision
from app.risk.manager import RiskManager


def _cfg(**overrides) -> RiskConfig:
    defaults = dict(
        initial_balance=1000.0,
        stake_mode="fixed",
        stake_fixed=10.0,
        stake_percent=1.0,
        max_daily_loss=50.0,
        max_consecutive_losses=3,
        cooldown_windows=2,
        loss_reduction_factor=0.5,
        slippage_pct=0.0,
    )
    defaults.update(overrides)
    return RiskConfig(**defaults)


class TestRiskManager:
    def test_initial_balance(self):
        rm = RiskManager(_cfg())
        assert rm.balance == pytest.approx(1000.0)

    def test_fixed_stake(self):
        rm = RiskManager(_cfg())
        stake = rm.compute_stake(Decision.UP)
        assert stake == pytest.approx(10.0)

    def test_percent_stake(self):
        rm = RiskManager(_cfg(stake_mode="percent", stake_percent=2.0))
        stake = rm.compute_stake(Decision.UP)
        assert stake == pytest.approx(20.0)

    def test_no_trade_returns_zero_stake(self):
        rm = RiskManager(_cfg())
        assert rm.compute_stake(Decision.NO_TRADE) == 0.0

    def test_win_resets_streak(self):
        rm = RiskManager(_cfg())
        rm.record_result(-10.0, is_correct=False)
        rm.record_result(-10.0, is_correct=False)
        assert rm.consecutive_losses == 2
        rm.record_result(10.0, is_correct=True)
        assert rm.consecutive_losses == 0

    def test_consecutive_losses_trigger_cooldown(self):
        rm = RiskManager(_cfg(max_consecutive_losses=3, cooldown_windows=2))
        for _ in range(3):
            rm.record_result(-10.0, is_correct=False)
        assert rm.is_in_cooldown

    def test_cooldown_blocks_stake(self):
        rm = RiskManager(_cfg(max_consecutive_losses=2, cooldown_windows=2))
        rm.record_result(-10.0, is_correct=False)
        rm.record_result(-10.0, is_correct=False)
        # Now in cooldown
        assert rm.compute_stake(Decision.UP) == 0.0

    def test_balance_updates_after_win(self):
        rm = RiskManager(_cfg())
        rm.record_result(10.0, is_correct=True)
        assert rm.balance == pytest.approx(1010.0)

    def test_balance_updates_after_loss(self):
        rm = RiskManager(_cfg())
        rm.record_result(-10.0, is_correct=False)
        assert rm.balance == pytest.approx(990.0)

    def test_daily_loss_limit_blocks_stake(self):
        rm = RiskManager(_cfg(max_daily_loss=20.0))
        rm.record_result(-25.0, is_correct=False)
        assert rm.compute_stake(Decision.UP) == 0.0

    def test_stake_reduced_after_losses(self):
        rm = RiskManager(_cfg(loss_reduction_factor=0.5))
        rm.record_result(-10.0, is_correct=False)  # 1 loss
        stake = rm.compute_stake(Decision.UP)
        assert stake < 10.0

    def test_slippage_applied_to_win(self):
        rm = RiskManager(_cfg(slippage_pct=1.0))
        pnl = rm.compute_pnl(stake=100.0, is_correct=True)
        assert pnl == pytest.approx(99.0)

    def test_slippage_applied_to_loss(self):
        rm = RiskManager(_cfg(slippage_pct=1.0))
        pnl = rm.compute_pnl(stake=100.0, is_correct=False)
        assert pnl == pytest.approx(-101.0)
