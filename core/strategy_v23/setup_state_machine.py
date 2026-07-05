from __future__ import annotations

from .models import Bar, Direction, Level, Setup


def is_sweep(bar: Bar, level: Level, side: Direction, tick_size: float) -> bool:
    if side == Direction.BUY:
        return bar.low < level.lower - tick_size and bar.close >= level.lower
    return bar.high > level.upper + tick_size and bar.close <= level.upper


def is_rejection(bar: Bar, level: Level, side: Direction, wick_ratio: float) -> bool:
    if bar.range <= 0 or not (level.lower <= bar.close <= level.upper):
        return False
    if side == Direction.BUY:
        return bar.lower_wick >= wick_ratio * bar.range
    return bar.upper_wick >= wick_ratio * bar.range


def start_setup(
    bar: Bar,
    level: Level,
    side: Direction,
    bar_index: int,
    tick_size: float,
    wick_ratio: float,
) -> Setup | None:
    swept = is_sweep(bar, level, side, tick_size)
    rejected = is_rejection(bar, level, side, wick_ratio)
    if not swept and not rejected:
        return None
    return Setup(
        level_id=level.identifier,
        level_kind=level.kind,
        level_direction=level.direction,
        lower=level.lower,
        upper=level.upper,
        side=side,
        touched_bar_index=bar_index,
        event_bar_index=bar_index,
        event_extreme=bar.low if side == Direction.BUY else bar.high,
        event_type="sweep" if swept else "rejection",
    )


def advance_setup(setup: Setup, bar: Bar) -> tuple[str, bool]:
    """Return (state, ready). State is active, invalidated, or ready."""
    if setup.side == Direction.BUY:
        setup.closes_below = setup.closes_below + 1 if bar.close < setup.lower else 0
        if setup.closes_below >= 2:
            return "invalidated", False
        if bar.close > setup.upper:
            setup.recovered = True
            setup.closes_above += 1
        else:
            setup.closes_above = 0
        ready = setup.recovered and setup.closes_above >= 2
    else:
        setup.closes_above = setup.closes_above + 1 if bar.close > setup.upper else 0
        if setup.closes_above >= 2:
            return "invalidated", False
        if bar.close < setup.lower:
            setup.recovered = True
            setup.closes_below += 1
        else:
            setup.closes_below = 0
        ready = setup.recovered and setup.closes_below >= 2
    return ("ready", True) if ready else ("active", False)

