from __future__ import annotations

from collections.abc import Iterable
import heapq

from .models import Direction, Level, LevelDirection


BUY_ONLY_KINDS = {
    "prior_low",
    "swing_low_1m",
    "swing_low_5m",
    "swing_low_15m",
    "ob_buy",
    "imbalance_buy",
    "vwap_minus1",
    "vwap_minus2",
    "operational_low",
    "sweep_low",
}

SELL_ONLY_KINDS = {
    "prior_high",
    "swing_high_1m",
    "swing_high_5m",
    "swing_high_15m",
    "ob_sell",
    "imbalance_sell",
    "vwap_plus1",
    "vwap_plus2",
    "operational_high",
    "sweep_high",
}

NEUTRAL_KINDS = {"cme_open", "vwap"}


def classify_level(kind: str, *, vwap_direction: LevelDirection = LevelDirection.NEUTRAL) -> LevelDirection:
    if kind == "vwap":
        return vwap_direction
    if kind in BUY_ONLY_KINDS:
        return LevelDirection.BUY_ONLY
    if kind in SELL_ONLY_KINDS:
        return LevelDirection.SELL_ONLY
    if kind in NEUTRAL_KINDS:
        return LevelDirection.NEUTRAL
    raise ValueError(f"Unknown v2.3 level kind: {kind}")


def side_allowed(level_direction: LevelDirection, side: Direction) -> bool:
    return level_direction == LevelDirection.NEUTRAL or (
        level_direction == LevelDirection.BUY_ONLY and side == Direction.BUY
    ) or (
        level_direction == LevelDirection.SELL_ONLY and side == Direction.SELL
    )


def vwap_cross_direction(
    previous_close: float | None,
    previous_vwap: float | None,
    current_close: float,
    current_vwap: float,
    current_direction: LevelDirection,
) -> LevelDirection:
    if previous_close is None or previous_vwap is None:
        return current_direction
    if previous_close <= previous_vwap and current_close > current_vwap:
        return LevelDirection.BUY_ONLY
    if previous_close >= previous_vwap and current_close < current_vwap:
        return LevelDirection.SELL_ONLY
    return current_direction


def resolve_direction_conflicts(levels: Iterable[Level], distance_points: float) -> set[str]:
    """Return identifiers suppressed by a newer/fresher opposing level."""
    active = sorted(
        (level for level in levels if level.active and level.direction != LevelDirection.NEUTRAL),
        key=lambda level: (level.lower, level.upper, level.identifier),
    )
    suppressed: set[str] = set()
    window: dict[str, Level] = {}
    expiry_heap: list[tuple[float, str]] = []
    for current in active:
        while expiry_heap and expiry_heap[0][0] < current.lower:
            _, identifier = heapq.heappop(expiry_heap)
            window.pop(identifier, None)
        for other in list(window.values()):
            if other.direction == current.direction:
                continue
            if other.upper + distance_points < current.lower:
                continue
            other_key = (other.created_at, -other.test_count, other.identifier)
            current_key = (current.created_at, -current.test_count, current.identifier)
            loser = other if current_key > other_key else current
            suppressed.add(loser.identifier)
        window[current.identifier] = current
        heapq.heappush(expiry_heap, (current.upper + distance_points, current.identifier))
    return suppressed
