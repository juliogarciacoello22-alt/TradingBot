from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .config import StrategyConfigV23
from .models import Bar, SignalDecision
from .strategy_core import StrategyCoreV23


class StrategyStreamV23:
    """Shared closed-bar interface for historical and future live consumers."""

    def __init__(self, config: StrategyConfigV23 | None = None):
        self.config = config or StrategyConfigV23()
        self.core = StrategyCoreV23(self.config)

    @property
    def rejections(self):
        return self.core.rejections

    def process_closed_bar(self, bar: Bar, *, position_open: bool = False) -> SignalDecision | None:
        return self.core.process_bar(bar, position_open=position_open)

    def process_live_payload(self, payload: dict, *, position_open: bool = False) -> SignalDecision | None:
        if not payload.get("isClosed", False):
            return None
        if payload.get("barType", "Minute") != "Minute" or int(payload.get("barSize", 1)) != 1:
            raise ValueError("BiUmolo v2.3 requires closed one-minute bars")
        timestamp = self._timestamp(payload["timestamp"])
        bar = Bar(
            timestamp=timestamp,
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=float(payload["volume"]),
        )
        if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high and bar.volume >= 0):
            raise ValueError("Invalid live OHLCV payload")
        return self.process_closed_bar(bar, position_open=position_open)

    def _timestamp(self, value) -> datetime:
        local_timezone = ZoneInfo(self.config.timezone)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).astimezone(local_timezone)
        timestamp = datetime.fromisoformat(str(value))
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=local_timezone)
        return timestamp.astimezone(local_timezone)
