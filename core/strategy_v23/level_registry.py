from __future__ import annotations

from datetime import datetime

from .direction_engine import classify_level
from .models import Bar, Level, LevelDirection, LevelState


class LevelRegistry:
    def __init__(self, tick_size: float):
        self.tick_size = tick_size
        self.levels: dict[str, Level] = {}
        self.dynamic: dict[str, Level] = {}

    def tick(self, value: float) -> float:
        return round(value / self.tick_size) * self.tick_size

    def add(
        self,
        kind: str,
        lower: float,
        upper: float,
        created_at: datetime,
        *,
        direction: LevelDirection | None = None,
        dynamic: bool = False,
        suffix: str = "",
    ) -> Level:
        lower, upper = self.tick(min(lower, upper)), self.tick(max(lower, upper))
        identifier = f"{kind}:{created_at.isoformat()}:{lower:.2f}:{upper:.2f}:{suffix}"
        level = Level(
            identifier=identifier,
            kind=kind,
            lower=lower,
            upper=upper,
            created_at=created_at,
            direction=direction or classify_level(kind),
            dynamic=dynamic,
        )
        target = self.dynamic if dynamic else self.levels
        target.setdefault(identifier, level)
        return target[identifier]

    def update_dynamic(
        self,
        kind: str,
        price: float,
        created_at: datetime,
        direction: LevelDirection | None = None,
    ) -> Level:
        identifier = f"dynamic:{kind}"
        center = self.tick(price)
        if identifier not in self.dynamic:
            self.dynamic[identifier] = Level(
                identifier=identifier,
                kind=kind,
                lower=center - self.tick_size,
                upper=center + self.tick_size,
                created_at=created_at,
                direction=direction or classify_level(kind),
                dynamic=True,
            )
        level = self.dynamic[identifier]
        level.lower = center - self.tick_size
        level.upper = center + self.tick_size
        if direction is not None:
            level.direction = direction
        return level

    def active(self) -> list[Level]:
        return [level for level in [*self.levels.values(), *self.dynamic.values()] if level.active]

    def reset_dynamic(self) -> None:
        self.dynamic.clear()

    def get(self, identifier: str) -> Level | None:
        return self.levels.get(identifier) or self.dynamic.get(identifier)

    def deactivate(self, identifier: str | None) -> None:
        if identifier and (level := self.get(identifier)):
            level.active = False
            level.state = LevelState.INVALID

    def touched(self, bar: Bar, level: Level, tolerance_ticks: int = 1) -> bool:
        tolerance = tolerance_ticks * self.tick_size
        return bar.high >= level.lower - tolerance and bar.low <= level.upper + tolerance

    def update_tests(self, bar: Bar, atr14: float | None, tolerance_ticks: int = 1) -> None:
        if atr14 is None:
            return
        for level in self.active():
            if level.created_at == bar.timestamp and level.kind.startswith(("imbalance_", "ob_")):
                continue
            overlap = self.touched(bar, level, tolerance_ticks)
            distance = 0.0 if overlap else min(abs(bar.low - level.upper), abs(bar.high - level.lower))
            if distance >= atr14:
                level.armed = True
            if level.armed and overlap:
                level.test_count += 1
                level.armed = False
                level.refresh_state()

    def update_zone_invalidations(self, bar: Bar) -> None:
        for level in self.active():
            if not level.kind.startswith(("imbalance_", "ob_")):
                continue
            if level.created_at == bar.timestamp:
                continue
            level.inside_closes = level.inside_closes + 1 if level.lower <= bar.close <= level.upper else 0
            if level.inside_closes >= 2:
                level.active = False
                level.state = LevelState.INVALID
