from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from core.strategy_v23.config import StrategyConfigV23
from core.strategy_v23.models import Bar, Direction, SignalDecision
from core.strategy_v23.price_math import clamp_to_range, round_to_tick


@dataclass
class Position:
    signal: SignalDecision
    opened_bar_index: int
    entry_timestamp: datetime


@dataclass(frozen=True)
class EntryAttempt:
    position: Position | None
    rejection_reason: str | None = None


@dataclass(frozen=True)
class TradeResult:
    sequence: int
    signal_timestamp: datetime
    entry_timestamp: datetime
    exit_timestamp: datetime | None
    side: Direction
    level_kind: str
    event_type: str
    entry: float
    stop: float
    tp1: float
    exit_price: float | None
    risk_points: float
    outcome: str
    gross_r: float
    exit_slippage_r: float
    commission_r: float
    net_r: float
    confirmations: tuple[str, ...]


class FillModel:
    def __init__(self, config: StrategyConfigV23):
        self.config = config

    def tick(self, value: float) -> float:
        return round_to_tick(value, self.config.tick_size)

    def reachable_price(self, desired: float, bar: Bar) -> float:
        return clamp_to_range(self.tick(desired), bar.low, bar.high)

    def open_next_bar(self, signal: SignalDecision, bar: Bar, bar_index: int) -> EntryAttempt:
        if bar.timestamp <= signal.timestamp:
            return EntryAttempt(None, "entry_not_after_signal")
        slip_points = self.config.entry_slippage_ticks * self.config.tick_size
        desired_entry = (
            bar.open + slip_points
            if signal.side == Direction.BUY
            else bar.open - slip_points
        )
        entry = self.reachable_price(
            desired_entry,
            bar,
        )
        risk = entry - signal.stop if signal.side == Direction.BUY else signal.stop - entry
        if risk <= 0:
            return EntryAttempt(None, "entry_gap_crossed_stop")
        if risk < self.config.min_stop_points or risk > self.config.max_stop_atr_multiple * signal.atr14:
            return EntryAttempt(None, "entry_gap_invalid_risk")
        tp1 = self.tick(
            entry + self.config.target_r * risk
            if signal.side == Direction.BUY
            else entry - self.config.target_r * risk
        )
        filled_signal = replace(
            signal,
            entry=entry,
            risk_points=risk,
            tp1=tp1,
            metadata={
                **signal.metadata,
                "entry_model": "next_bar_open",
                "signal_timestamp": signal.timestamp.isoformat(),
            },
        )
        return EntryAttempt(Position(filled_signal, bar_index, bar.timestamp))

    def resolve(self, position: Position, bar: Bar, bar_index: int) -> TradeResult | None:
        signal = position.signal
        if signal.side == Direction.BUY:
            stop_hit = bar.low <= signal.stop
            target_hit = bar.high >= signal.tp1
        else:
            stop_hit = bar.high >= signal.stop
            target_hit = bar.low <= signal.tp1
        if not stop_hit and not target_hit:
            return None
        outcome = "STOP" if stop_hit else "TP1"  # stop-first conflict rule
        if stop_hit and signal.side == Direction.BUY:
            theoretical_exit = min(signal.stop, bar.open)
        elif stop_hit:
            theoretical_exit = max(signal.stop, bar.open)
        else:
            theoretical_exit = signal.tp1
        slip_points = self.config.exit_slippage_ticks * self.config.tick_size
        desired_exit = (
            theoretical_exit - slip_points
            if signal.side == Direction.BUY
            else theoretical_exit + slip_points
        )
        exit_price = self.reachable_price(desired_exit, bar)
        price_r = (
            (exit_price - signal.entry) / signal.risk_points
            if signal.side == Direction.BUY
            else (signal.entry - exit_price) / signal.risk_points
        )
        applied_exit_slippage = (
            theoretical_exit - exit_price
            if signal.side == Direction.BUY
            else exit_price - theoretical_exit
        )
        exit_slippage_r = applied_exit_slippage / signal.risk_points
        commission_r = (
            self.config.commission_round_trip / (signal.risk_points * self.config.point_value)
            if signal.risk_points > 0 else 0.0
        )
        return TradeResult(
            sequence=signal.sequence,
            signal_timestamp=signal.timestamp,
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=bar.timestamp,
            side=signal.side,
            level_kind=signal.level_kind,
            event_type=signal.event_type,
            entry=signal.entry,
            stop=signal.stop,
            tp1=signal.tp1,
            exit_price=exit_price,
            risk_points=signal.risk_points,
            outcome=outcome,
            gross_r=price_r + exit_slippage_r,
            exit_slippage_r=exit_slippage_r,
            commission_r=commission_r,
            net_r=price_r - commission_r,
            confirmations=signal.confirmations,
        )

    def mark_open(self, position: Position) -> TradeResult:
        signal = position.signal
        return TradeResult(
            sequence=signal.sequence,
            signal_timestamp=signal.timestamp,
            entry_timestamp=position.entry_timestamp,
            exit_timestamp=None,
            side=signal.side,
            level_kind=signal.level_kind,
            event_type=signal.event_type,
            entry=signal.entry,
            stop=signal.stop,
            tp1=signal.tp1,
            exit_price=None,
            risk_points=signal.risk_points,
            outcome="OPEN",
            gross_r=0.0,
            exit_slippage_r=0.0,
            commission_r=0.0,
            net_r=0.0,
            confirmations=signal.confirmations,
        )
