"""Trade record model."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from app.models.signal import Decision, MarketRegime


@dataclass
class TradeRecord:
    """Complete record of a single paper-trade window."""

    id: int
    window_start: datetime
    window_end: datetime
    open_price: float
    close_price: Optional[float]
    decision: Decision
    actual_outcome: Optional[Decision]    # UP or DOWN after resolution
    confidence: float
    regime: MarketRegime
    signal_scores: Dict[str, float]
    reason: str
    stake: float
    pnl: float
    balance_after: float
    is_correct: Optional[bool]
    notes: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        """Serialize to plain dictionary for CSV/JSON export."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "open_price": self.open_price,
            "close_price": self.close_price,
            "decision": self.decision.value,
            "actual_outcome": self.actual_outcome.value if self.actual_outcome else None,
            "confidence": round(self.confidence, 2),
            "regime": self.regime.value,
            "signal_scores": {k: round(v, 4) for k, v in self.signal_scores.items()},
            "reason": self.reason,
            "stake": round(self.stake, 2),
            "pnl": round(self.pnl, 2),
            "balance_after": round(self.balance_after, 2),
            "is_correct": self.is_correct,
            "notes": self.notes,
        }
