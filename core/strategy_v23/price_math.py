from __future__ import annotations

import math


def round_to_tick(value: float, tick_size: float) -> float:
    """Round midpoint prices upward using one policy across strategy and fills."""
    if tick_size <= 0:
        raise ValueError("tick_size must be positive")
    return math.floor(value / tick_size + 0.5) * tick_size


def clamp_to_range(value: float, lower: float, upper: float) -> float:
    if lower > upper:
        raise ValueError("lower cannot exceed upper")
    return min(max(value, lower), upper)
