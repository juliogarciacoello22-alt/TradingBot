from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class StrategyConfigV23:
    version: str = "2.3"
    timezone: str = "America/Chicago"
    tick_size: float = 0.25
    atr_period: int = 14
    volume_period: int = 20
    point_level_half_width_ticks: int = 1
    level_touch_tolerance_ticks: int = 1
    rejection_wick_ratio: float = 0.40
    imbalance_body_ratio: float = 0.60
    imbalance_atr_multiple: float = 1.50
    setup_expiry_bars: int = 10
    min_confirmations: int = 2
    min_stop_points: float = 1.0
    max_stop_atr_multiple: float = 2.0
    target_r: float = 1.5
    max_signals_per_day: int = 3
    cooldown_minutes: int = 20
    conflict_distance_points: float = 1.0
    signal_start_hour: int = 8
    signal_start_minute: int = 30
    signal_end_hour: int = 11
    signal_end_minute: int = 0
    statistics_start_date: str = "2025-11-04"
    entry_slippage_ticks: int = 1
    exit_slippage_ticks: int = 0
    commission_round_trip: float = 0.0
    point_value: float = 20.0

    def as_dict(self) -> dict:
        return asdict(self)

