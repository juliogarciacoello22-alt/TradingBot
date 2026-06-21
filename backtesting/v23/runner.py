from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from core.strategy_v23.config import StrategyConfigV23
from core.strategy_v23.models import Bar, Rejection, SignalDecision
from core.strategy_v23.strategy_core import StrategyCoreV23

from .data_loader import LoadedDataset
from .fill_model import FillModel, Position, TradeResult
from .historical_clock import HistoricalClock
from .metrics import calculate_metrics


@dataclass(frozen=True)
class BacktestResult:
    manifest: dict
    signals: tuple[SignalDecision, ...]
    rejections: tuple
    trades: tuple[TradeResult, ...]
    summary: dict
    daily: tuple[dict, ...]
    equity_curve: tuple[dict, ...]


class BacktestRunnerV23:
    def __init__(self, config: StrategyConfigV23 | None = None):
        self.config = config or StrategyConfigV23()

    def run(self, dataset: LoadedDataset) -> BacktestResult:
        core = StrategyCoreV23(self.config)
        clock = HistoricalClock()
        fills = FillModel(self.config)
        signals: list[SignalDecision] = []
        trades: list[TradeResult] = []
        position: Position | None = None
        pending_signal: SignalDecision | None = None
        execution_rejections: list[Rejection] = []

        for index, bar in enumerate(dataset.bars):
            clock.advance(bar.timestamp)
            was_exposed = position is not None
            if pending_signal is not None:
                if position is not None:
                    raise AssertionError("Pending entry exists while a position is open")
                attempt = fills.open_next_bar(pending_signal, bar, index)
                if attempt.position is None:
                    execution_rejections.append(Rejection(
                        bar.timestamp,
                        attempt.rejection_reason or "entry_rejected",
                        pending_signal.level_kind,
                        pending_signal.side,
                    ))
                else:
                    position = attempt.position
                    was_exposed = True
                pending_signal = None
            if position is not None:
                result = fills.resolve(position, bar, index)
                if result is not None:
                    trades.append(result)
                    position = None
            decision = core.process_bar(bar, position_open=was_exposed)
            if decision is not None:
                if position is not None or pending_signal is not None:
                    raise AssertionError("Strategy emitted a signal while exposure exists")
                signals.append(decision)
                pending_signal = decision
        if position is not None:
            trades.append(fills.mark_open(position))
        if pending_signal is not None:
            execution_rejections.append(Rejection(
                dataset.bars[-1].timestamp,
                "entry_unfilled_end_of_data",
                pending_signal.level_kind,
                pending_signal.side,
            ))

        rejections = [*core.rejections, *execution_rejections]

        summary, daily, curve = calculate_metrics(
            trades,
            statistics_start_date=self.config.statistics_start_date,
            all_dates=sorted({bar.timestamp.date().isoformat() for bar in dataset.bars}),
            rejections=rejections,
        )
        config_json = json.dumps(self.config.as_dict(), sort_keys=True, separators=(",", ":"))
        manifest = {
            "strategy": "BiUmolo",
            "strategy_version": self.config.version,
            "dataset_path": str(dataset.path),
            "dataset_sha256": dataset.sha256,
            "bar_count": len(dataset.bars),
            "first_timestamp": dataset.bars[0].timestamp.isoformat(),
            "last_timestamp": dataset.bars[-1].timestamp.isoformat(),
            "execution_model": {
                "entry": "next_bar_open_plus_adverse_slippage",
                "stop_gap": "adverse_bar_open_plus_exit_slippage",
                "intrabar_conflict": "stop_first",
            },
            "config": self.config.as_dict(),
            "config_sha256": hashlib.sha256(config_json.encode()).hexdigest().upper(),
        }
        return BacktestResult(
            manifest=manifest,
            signals=tuple(signals),
            rejections=tuple(rejections),
            trades=tuple(trades),
            summary=summary,
            daily=tuple(daily),
            equity_curve=tuple(curve),
        )
