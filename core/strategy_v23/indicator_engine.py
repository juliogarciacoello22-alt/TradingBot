from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from statistics import mean

from .models import Bar


class WilderATR:
    def __init__(self, period: int):
        self.period = period
        self._seed: list[float] = []
        self.value: float | None = None
        self.previous_close: float | None = None
        self.history: list[float | None] = []

    def update(self, bar: Bar) -> float | None:
        true_range = bar.high - bar.low
        if self.previous_close is not None:
            true_range = max(
                true_range,
                abs(bar.high - self.previous_close),
                abs(bar.low - self.previous_close),
            )
        self.previous_close = bar.close
        if self.value is None:
            self._seed.append(true_range)
            if len(self._seed) == self.period:
                self.value = mean(self._seed)
        else:
            self.value += (true_range - self.value) / self.period
        self.history.append(self.value)
        return self.value


class SessionVWAP:
    def __init__(self):
        self.session = None
        self.volume = 0.0
        self.price_volume = 0.0
        self.price2_volume = 0.0

    def update(self, session, bar: Bar) -> tuple[float, float]:
        if session != self.session:
            self.session = session
            self.volume = self.price_volume = self.price2_volume = 0.0
        typical = (bar.high + bar.low + bar.close) / 3.0
        self.volume += bar.volume
        self.price_volume += typical * bar.volume
        self.price2_volume += typical * typical * bar.volume
        if self.volume <= 0:
            return typical, 0.0
        vwap = self.price_volume / self.volume
        variance = max(0.0, self.price2_volume / self.volume - vwap * vwap)
        return vwap, math.sqrt(variance)


class BarAggregator:
    def __init__(self, minutes: int):
        self.minutes = minutes
        self.current: Bar | None = None
        self.bucket = None
        self.completed: list[Bar] = []

    def _bucket(self, bar: Bar):
        return bar.timestamp.replace(
            minute=(bar.timestamp.minute // self.minutes) * self.minutes,
            second=0,
            microsecond=0,
        )

    def update(self, bar: Bar) -> bool:
        bucket = self._bucket(bar)
        if self.current is None:
            self.bucket = bucket
            self.current = Bar(bucket, bar.open, bar.high, bar.low, bar.close, bar.volume)
            return False
        if bucket == self.bucket:
            self.current = Bar(
                self.current.timestamp,
                self.current.open,
                max(self.current.high, bar.high),
                min(self.current.low, bar.low),
                bar.close,
                self.current.volume + bar.volume,
            )
            return False
        self.completed.append(self.current)
        self.bucket = bucket
        self.current = Bar(bucket, bar.open, bar.high, bar.low, bar.close, bar.volume)
        return True


@dataclass(frozen=True)
class IndicatorSnapshot:
    atr14: float | None
    atr_five_bars_ago: float | None
    volume20: float | None
    vwap: float
    sigma: float
    completed_5m: bool
    completed_15m: bool


@dataclass
class IndicatorEngine:
    atr_period: int = 14
    volume_period: int = 20
    atr: WilderATR = field(init=False)
    vwap: SessionVWAP = field(default_factory=SessionVWAP)
    aggregation_5m: BarAggregator = field(default_factory=lambda: BarAggregator(5))
    aggregation_15m: BarAggregator = field(default_factory=lambda: BarAggregator(15))
    volumes: deque = field(init=False)

    def __post_init__(self):
        self.atr = WilderATR(self.atr_period)
        self.volumes = deque(maxlen=self.volume_period)

    def update(self, session, bar: Bar) -> IndicatorSnapshot:
        volume20 = mean(self.volumes) if len(self.volumes) == self.volume_period else None
        atr14 = self.atr.update(bar)
        atr_old = self.atr.history[-6] if len(self.atr.history) >= 6 else None
        vwap, sigma = self.vwap.update(session, bar)
        completed_5m = self.aggregation_5m.update(bar)
        completed_15m = self.aggregation_15m.update(bar)
        self.volumes.append(bar.volume)
        return IndicatorSnapshot(
            atr14=atr14,
            atr_five_bars_ago=atr_old,
            volume20=volume20,
            vwap=vwap,
            sigma=sigma,
            completed_5m=completed_5m,
            completed_15m=completed_15m,
        )


def confirmed_pivot(series: list[Bar]) -> tuple[Bar, bool, bool] | None:
    if len(series) < 5:
        return None
    index = len(series) - 3
    pivot = series[index]
    neighbors = series[index - 2:index] + series[index + 1:index + 3]
    is_high = pivot.high > max(bar.high for bar in neighbors)
    is_low = pivot.low < min(bar.low for bar in neighbors)
    return pivot, is_high, is_low

