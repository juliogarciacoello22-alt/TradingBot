from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class LevelDirection(str, Enum):
    BUY_ONLY = "BUY_ONLY"
    SELL_ONLY = "SELL_ONLY"
    NEUTRAL = "NEUTRAL"


class LevelState(str, Enum):
    FRESH = "fresh"
    VALID = "valid"
    WEAKENED = "weakened"
    INVALID = "invalid"


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body_ratio(self) -> float:
        return abs(self.close - self.open) / self.range if self.range else 0.0

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)


@dataclass
class Level:
    identifier: str
    kind: str
    lower: float
    upper: float
    created_at: datetime
    direction: LevelDirection
    test_count: int = 0
    state: LevelState = LevelState.FRESH
    armed: bool = False
    active: bool = True
    inside_closes: int = 0
    dynamic: bool = False

    @property
    def midpoint(self) -> float:
        return (self.lower + self.upper) / 2.0

    def refresh_state(self) -> None:
        if self.test_count == 0:
            self.state = LevelState.FRESH
        elif self.test_count == 1:
            self.state = LevelState.VALID
        elif self.test_count == 2:
            self.state = LevelState.WEAKENED
        else:
            self.state = LevelState.INVALID
            self.active = False


@dataclass
class Setup:
    level_id: str
    level_kind: str
    level_direction: LevelDirection
    lower: float
    upper: float
    side: Direction
    touched_bar_index: int
    event_bar_index: int
    event_extreme: float
    event_type: str
    recovered: bool = False
    closes_above: int = 0
    closes_below: int = 0


@dataclass(frozen=True)
class SignalDecision:
    timestamp: datetime
    side: Direction
    level_id: str
    level_kind: str
    event_type: str
    entry: float
    stop: float
    risk_points: float
    tp1: float
    atr14: float
    volume: float
    volume20: float | None
    confirmations: tuple[str, ...]
    sequence: int
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Rejection:
    timestamp: datetime
    reason: str
    level_kind: str | None = None
    side: Direction | None = None

