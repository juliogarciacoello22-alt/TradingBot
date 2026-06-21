from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.strategy_v23.config import StrategyConfigV23
from core.strategy_v23.models import Bar, Direction, SignalDecision


@dataclass
class Position:
    signal: SignalDecision
    opened_bar_index: int


@dataclass(frozen=True)
class TradeResult:
    sequence: int
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

    def open(self, signal: SignalDecision, bar_index: int) -> Position:
        return Position(signal, bar_index)

    def resolve(self, position: Position, bar: Bar, bar_index: int) -> TradeResult | None:
        if bar_index <= position.opened_bar_index:
            return None
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
        theoretical_exit = signal.stop if stop_hit else signal.tp1
        slip_points = self.config.exit_slippage_ticks * self.config.tick_size
        exit_price = theoretical_exit
        if slip_points:
            exit_price = theoretical_exit - slip_points if signal.side == Direction.BUY else theoretical_exit + slip_points
        price_r = (
            (exit_price - signal.entry) / signal.risk_points
            if signal.side == Direction.BUY
            else (signal.entry - exit_price) / signal.risk_points
        )
        exit_slippage_r = slip_points / signal.risk_points
        commission_r = (
            self.config.commission_round_trip / (signal.risk_points * self.config.point_value)
            if signal.risk_points > 0 else 0.0
        )
        return TradeResult(
            sequence=signal.sequence,
            entry_timestamp=signal.timestamp,
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
            entry_timestamp=signal.timestamp,
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

