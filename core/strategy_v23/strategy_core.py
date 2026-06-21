from __future__ import annotations

import math
from collections import Counter
from datetime import date, time

from .config import StrategyConfigV23
from .confirmation_engine import confirmations
from .direction_engine import (
    classify_level,
    resolve_direction_conflicts,
    side_allowed,
    vwap_cross_direction,
)
from .indicator_engine import IndicatorEngine, confirmed_pivot
from .level_registry import LevelRegistry
from .models import (
    Bar,
    Direction,
    LevelDirection,
    LevelState,
    Rejection,
    Setup,
    SignalDecision,
)
from .session_engine import cme_session_date, in_signal_window
from .setup_state_machine import advance_setup, start_setup


class StrategyCoreV23:
    """Pure causal strategy. It has no files, network, or wall-clock access."""

    def __init__(self, config: StrategyConfigV23 | None = None):
        self.config = config or StrategyConfigV23()
        self.indicators = IndicatorEngine(self.config.atr_period, self.config.volume_period)
        self.levels = LevelRegistry(self.config.tick_size)
        self.bars: list[Bar] = []
        self.swing_highs_1m: list[float] = []
        self.swing_lows_1m: list[float] = []
        self.setups: dict[tuple[str, Direction], Setup] = {}
        self.rejections: list[Rejection] = []
        self.signal_counts: Counter[str] = Counter()
        self.last_signal_at = {}
        self.sequence = 0

        self.current_cme_session = None
        self.cme_high = None
        self.cme_low = None
        self.previous_cme_range = None
        self.current_operational_date: date | None = None
        self.operational_high = None
        self.operational_low = None
        self.published_operational_high = None
        self.published_operational_low = None
        self.operational_high_level_id = None
        self.operational_low_level_id = None
        self.previous_close = None
        self.previous_vwap = None
        self.vwap_direction = LevelDirection.NEUTRAL

    def tick(self, value: float) -> float:
        return math.floor(value / self.config.tick_size + 0.5) * self.config.tick_size

    def _point_level(self, kind: str, price: float, timestamp, *, direction=None):
        half_width = self.config.point_level_half_width_ticks * self.config.tick_size
        return self.levels.add(
            kind,
            price - half_width,
            price + half_width,
            timestamp,
            direction=direction,
        )

    def _start_session(self, session, bar: Bar) -> None:
        if self.current_cme_session is not None:
            self.previous_cme_range = (self.cme_high, self.cme_low)
        self.current_cme_session = session
        self.cme_high, self.cme_low = bar.high, bar.low
        self.levels.reset_dynamic()
        self.vwap_direction = LevelDirection.NEUTRAL
        self.previous_close = self.previous_vwap = None
        self._point_level("cme_open", bar.open, bar.timestamp)
        if self.previous_cme_range:
            previous_high, previous_low = self.previous_cme_range
            self._point_level("prior_high", previous_high, bar.timestamp)
            self._point_level("prior_low", previous_low, bar.timestamp)

    def _update_operational_levels_before_bar(self, bar: Bar) -> None:
        if self.current_operational_date != bar.timestamp.date():
            self.current_operational_date = bar.timestamp.date()
            self.operational_high = self.operational_low = None
            self.published_operational_high = self.published_operational_low = None
            self.levels.deactivate(self.operational_high_level_id)
            self.levels.deactivate(self.operational_low_level_id)
            self.operational_high_level_id = self.operational_low_level_id = None
        if not (time(6, 30) <= bar.timestamp.time() <= time(16, 0)):
            return
        if self.operational_high is not None and self.operational_high != self.published_operational_high:
            self.levels.deactivate(self.operational_high_level_id)
            level = self._point_level("operational_high", self.operational_high, bar.timestamp)
            self.operational_high_level_id = level.identifier
            self.published_operational_high = self.operational_high
        if self.operational_low is not None and self.operational_low != self.published_operational_low:
            self.levels.deactivate(self.operational_low_level_id)
            level = self._point_level("operational_low", self.operational_low, bar.timestamp)
            self.operational_low_level_id = level.identifier
            self.published_operational_low = self.operational_low

    def _update_operational_extrema_after_bar(self, bar: Bar) -> None:
        if time(6, 30) <= bar.timestamp.time() <= time(16, 0):
            self.operational_high = bar.high if self.operational_high is None else max(self.operational_high, bar.high)
            self.operational_low = bar.low if self.operational_low is None else min(self.operational_low, bar.low)

    def _update_pivots(self, snapshot, bar: Bar) -> None:
        if snapshot.completed_5m:
            pivot = confirmed_pivot(self.indicators.aggregation_5m.completed)
            if pivot:
                candle, is_high, is_low = pivot
                if is_high:
                    self._point_level("swing_high_5m", candle.high, bar.timestamp)
                if is_low:
                    self._point_level("swing_low_5m", candle.low, bar.timestamp)
        if snapshot.completed_15m:
            pivot = confirmed_pivot(self.indicators.aggregation_15m.completed)
            if pivot:
                candle, is_high, is_low = pivot
                if is_high:
                    self._point_level("swing_high_15m", candle.high, bar.timestamp)
                if is_low:
                    self._point_level("swing_low_15m", candle.low, bar.timestamp)
        if len(self.bars) >= 5:
            index = len(self.bars) - 3
            candle = self.bars[index]
            neighbors = self.bars[index - 2:index] + self.bars[index + 1:index + 3]
            if candle.high > max(item.high for item in neighbors):
                self.swing_highs_1m.append(candle.high)
            if candle.low < min(item.low for item in neighbors):
                self.swing_lows_1m.append(candle.low)

    def _create_imbalance_and_ob(self, bar: Bar, atr14: float | None) -> None:
        if atr14 and bar.range >= self.config.imbalance_atr_multiple * atr14 and bar.body_ratio >= self.config.imbalance_body_ratio:
            kind = "imbalance_buy" if bar.close > bar.open else "imbalance_sell"
            self.levels.add(kind, bar.open, bar.close, bar.timestamp)
        if len(self.bars) < 3:
            return
        order_bar, impulse_1, impulse_2 = self.bars[-3:]
        if order_bar.close < order_bar.open and impulse_1.close > order_bar.high and impulse_2.close > impulse_1.high:
            self.levels.add("ob_buy", order_bar.open, order_bar.high, bar.timestamp)
        if order_bar.close > order_bar.open and impulse_1.close < order_bar.low and impulse_2.close < impulse_1.low:
            self.levels.add("ob_sell", order_bar.low, order_bar.open, bar.timestamp)

    def _update_dynamic_levels(self, bar: Bar, vwap: float, sigma: float) -> None:
        self.vwap_direction = vwap_cross_direction(
            self.previous_close,
            self.previous_vwap,
            bar.close,
            vwap,
            self.vwap_direction,
        )
        self.levels.update_dynamic("vwap", vwap, bar.timestamp, self.vwap_direction)
        self.levels.update_dynamic("vwap_plus1", vwap + sigma, bar.timestamp)
        self.levels.update_dynamic("vwap_minus1", vwap - sigma, bar.timestamp)
        self.levels.update_dynamic("vwap_plus2", vwap + 2 * sigma, bar.timestamp)
        self.levels.update_dynamic("vwap_minus2", vwap - 2 * sigma, bar.timestamp)
        self.previous_close, self.previous_vwap = bar.close, vwap

    def _reject(self, bar: Bar, reason: str, setup: Setup | None = None) -> None:
        self.rejections.append(Rejection(
            bar.timestamp,
            reason,
            setup.level_kind if setup else None,
            setup.side if setup else None,
        ))

    def _advance_setups(self, bar: Bar, bar_index: int) -> list[Setup]:
        ready: list[Setup] = []
        for key, setup in list(self.setups.items()):
            level = self.levels.get(setup.level_id)
            if bar_index - setup.touched_bar_index >= self.config.setup_expiry_bars:
                self._reject(bar, "setup_expired", setup)
                self.setups.pop(key)
                continue
            if level is None or not level.active:
                self._reject(bar, "level_invalidated", setup)
                self.setups.pop(key)
                continue
            state, is_ready = advance_setup(setup, bar)
            if state == "invalidated":
                self._reject(bar, "opposite_acceptance", setup)
                self.setups.pop(key)
            elif is_ready:
                ready.append(setup)
                self.setups.pop(key)
        return ready

    def _obstacle_before_target(self, setup: Setup, entry: float, tp1: float, suppressed: set[str]) -> bool:
        opposing = LevelDirection.SELL_ONLY if setup.side == Direction.BUY else LevelDirection.BUY_ONLY
        for level in self.levels.active():
            if level.identifier in suppressed or level.identifier == setup.level_id or level.direction != opposing:
                continue
            if setup.side == Direction.BUY and entry < level.lower < tp1:
                return True
            if setup.side == Direction.SELL and tp1 < level.upper < entry:
                return True
        return False

    def _evaluate_ready(
        self,
        bar: Bar,
        ready: list[Setup],
        snapshot,
        suppressed: set[str],
        position_open: bool,
    ) -> SignalDecision | None:
        day_key = bar.timestamp.date().isoformat()
        window_start = time(self.config.signal_start_hour, self.config.signal_start_minute)
        window_end = time(self.config.signal_end_hour, self.config.signal_end_minute)
        if not in_signal_window(bar.timestamp, window_start, window_end):
            for setup in ready:
                self._reject(bar, "outside_signal_window", setup)
            return None
        if position_open:
            for setup in ready:
                self._reject(bar, "position_open", setup)
            return None
        if self.signal_counts[day_key] >= self.config.max_signals_per_day:
            for setup in ready:
                self._reject(bar, "daily_signal_limit", setup)
            return None
        previous_signal = self.last_signal_at.get(day_key)
        if previous_signal and (bar.timestamp - previous_signal).total_seconds() < self.config.cooldown_minutes * 60:
            for setup in ready:
                self._reject(bar, "cooldown", setup)
            return None

        valid = []
        for setup in ready:
            if setup.level_id in suppressed:
                self._reject(bar, "direction_conflict", setup)
                continue
            level = self.levels.get(setup.level_id)
            if level is None or not side_allowed(level.direction, setup.side):
                self._reject(bar, "direction_not_allowed", setup)
                continue
            confirms = confirmations(
                bar=bar,
                setup=setup,
                swing_highs=self.swing_highs_1m,
                swing_lows=self.swing_lows_1m,
                volume20=snapshot.volume20,
                atr14=snapshot.atr14,
                atr_five_bars_ago=snapshot.atr_five_bars_ago,
            )
            if len(confirms) < self.config.min_confirmations:
                self._reject(bar, "insufficient_confirmations", setup)
                continue
            # Reference price only. The backtester fills the market order at the
            # next bar open and applies entry slippage there.
            entry = self.tick(bar.close)
            stop = self.tick(setup.event_extreme - self.config.tick_size if setup.side == Direction.BUY else setup.event_extreme + self.config.tick_size)
            risk = entry - stop if setup.side == Direction.BUY else stop - entry
            if snapshot.atr14 is None or risk < self.config.min_stop_points or risk > self.config.max_stop_atr_multiple * snapshot.atr14:
                self._reject(bar, "invalid_stop", setup)
                continue
            tp1 = self.tick(entry + self.config.target_r * risk if setup.side == Direction.BUY else entry - self.config.target_r * risk)
            if self._obstacle_before_target(setup, entry, tp1, suppressed):
                self._reject(bar, "opposing_level_before_tp1", setup)
                continue
            distance = abs(bar.close - (setup.lower + setup.upper) / 2.0)
            valid.append((len(confirms), -distance, setup.level_id, setup, entry, stop, risk, tp1, confirms))
        if not valid:
            return None
        _, _, _, setup, entry, stop, risk, tp1, confirms = max(valid, key=lambda item: item[:3])
        self.sequence += 1
        self.signal_counts[day_key] += 1
        self.last_signal_at[day_key] = bar.timestamp
        return SignalDecision(
            timestamp=bar.timestamp,
            side=setup.side,
            level_id=setup.level_id,
            level_kind=setup.level_kind,
            event_type=setup.event_type,
            entry=entry,
            stop=stop,
            risk_points=risk,
            tp1=tp1,
            atr14=snapshot.atr14,
            volume=bar.volume,
            volume20=snapshot.volume20,
            confirmations=confirms,
            sequence=self.sequence,
            metadata={
                "strategy_version": self.config.version,
                "entry_model": "next_bar_open_pending",
                "reference_price": "signal_bar_close",
            },
        )

    def _start_new_setups(self, bar: Bar, bar_index: int, suppressed: set[str]) -> None:
        for level in list(self.levels.active()):
            if level.identifier in suppressed or level.state not in {LevelState.FRESH, LevelState.VALID}:
                continue
            if not self.levels.touched(bar, level, self.config.level_touch_tolerance_ticks):
                continue
            if level.created_at == bar.timestamp and level.kind.startswith(("imbalance_", "ob_")):
                continue
            for side in (Direction.BUY, Direction.SELL):
                if not side_allowed(level.direction, side):
                    continue
                key = (level.identifier, side)
                if key in self.setups:
                    continue
                setup = start_setup(
                    bar,
                    level,
                    side,
                    bar_index,
                    self.config.tick_size,
                    self.config.rejection_wick_ratio,
                )
                if setup is None:
                    continue
                self.setups[key] = setup
                sweep_kind = "sweep_low" if side == Direction.BUY else "sweep_high"
                self._point_level(sweep_kind, setup.event_extreme, bar.timestamp)

    def process_bar(self, bar: Bar, *, position_open: bool = False) -> SignalDecision | None:
        if self.bars and bar.timestamp <= self.bars[-1].timestamp:
            raise ValueError("Bars must be strictly increasing and unique")
        self._update_operational_levels_before_bar(bar)
        self.bars.append(bar)
        bar_index = len(self.bars) - 1

        session = cme_session_date(bar.timestamp)
        if session != self.current_cme_session:
            self._start_session(session, bar)
        else:
            self.cme_high = max(self.cme_high, bar.high)
            self.cme_low = min(self.cme_low, bar.low)

        snapshot = self.indicators.update(session, bar)
        self._update_dynamic_levels(bar, snapshot.vwap, snapshot.sigma)
        self._update_pivots(snapshot, bar)
        self._create_imbalance_and_ob(bar, snapshot.atr14)
        self.levels.update_zone_invalidations(bar)
        self.levels.update_tests(bar, snapshot.atr14, self.config.level_touch_tolerance_ticks)

        ready = self._advance_setups(bar, bar_index)
        suppressed = resolve_direction_conflicts(self.levels.active(), self.config.conflict_distance_points)
        decision = self._evaluate_ready(bar, ready, snapshot, suppressed, position_open)
        self._start_new_setups(bar, bar_index, suppressed)
        self._update_operational_extrema_after_bar(bar)
        return decision
