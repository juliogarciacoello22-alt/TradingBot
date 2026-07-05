from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime

from core.strategy_v23.config import StrategyConfigV23
from core.strategy_v23.models import Bar, Rejection, SignalDecision
from core.strategy_v23.streaming_adapter import StrategyStreamV23

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


@dataclass(frozen=True)
class RunMetadata:
    commit_hash: str
    execution_timestamp: datetime

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-fA-F]{7,64}", self.commit_hash):
            raise ValueError("commit_hash must be a 7-64 character hexadecimal Git hash")
        if self.execution_timestamp.tzinfo is None:
            raise ValueError("execution_timestamp must be timezone-aware")


def sort_rejections(rejections: list[Rejection]) -> list[Rejection]:
    unique: dict[str, Rejection] = {}
    for rejection in rejections:
        existing = unique.get(rejection.event_id)
        if existing is not None and existing != rejection:
            raise AssertionError(f"Rejection event_id collision: {rejection.event_id}")
        unique[rejection.event_id] = rejection
    return sorted(
        unique.values(),
        key=lambda item: (
            item.timestamp,
            item.reason,
            item.level_kind or "",
            item.side.value if item.side else "",
        ),
    )


class BacktestRunnerV23:
    def __init__(self, config: StrategyConfigV23 | None = None):
        self.config = config or StrategyConfigV23()

    def run(self, dataset: LoadedDataset, *, metadata: RunMetadata) -> BacktestResult:
        strategy = StrategyStreamV23(self.config)
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
                        timestamp=bar.timestamp,
                        reason=attempt.rejection_reason or "entry_rejected",
                        level_kind=pending_signal.level_kind,
                        side=pending_signal.side,
                        level_id=pending_signal.level_id,
                        setup_id=pending_signal.metadata.get("setup_id"),
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
            decision = strategy.process_closed_bar(bar, position_open=was_exposed)
            if decision is not None:
                if position is not None or pending_signal is not None:
                    raise AssertionError("Strategy emitted a signal while exposure exists")
                signals.append(decision)
                pending_signal = decision
        if position is not None:
            trades.append(fills.mark_open(position))
        if pending_signal is not None:
            execution_rejections.append(Rejection(
                timestamp=dataset.bars[-1].timestamp,
                reason="entry_unfilled_end_of_data",
                level_kind=pending_signal.level_kind,
                side=pending_signal.side,
                level_id=pending_signal.level_id,
                setup_id=pending_signal.metadata.get("setup_id"),
            ))

        rejections = sort_rejections([*strategy.rejections, *execution_rejections])

        summary, daily, curve = calculate_metrics(
            trades,
            statistics_start_date=self.config.statistics_start_date,
            all_dates=sorted({bar.timestamp.date().isoformat() for bar in dataset.bars}),
            rejections=rejections,
        )
        config_json = json.dumps(self.config.as_dict(), sort_keys=True, separators=(",", ":"))
        gap_counts: dict[str, int] = {}
        for gap in dataset.gaps:
            gap_counts[gap.classification] = gap_counts.get(gap.classification, 0) + 1
        manifest = {
            "strategy": "BiUmolo",
            "strategy_version": self.config.version,
            "dataset_path": str(dataset.path),
            "dataset_sha256": dataset.sha256,
            "closure_calendar_sha256": dataset.closure_calendar_sha256,
            "commit_hash": metadata.commit_hash,
            "execution_timestamp": metadata.execution_timestamp.isoformat(),
            "bar_count": len(dataset.bars),
            "first_timestamp": dataset.bars[0].timestamp.isoformat(),
            "last_timestamp": dataset.bars[-1].timestamp.isoformat(),
            "gap_audit": {
                "accepted_gap_count": len(dataset.gaps),
                "classifications": dict(sorted(gap_counts.items())),
                "maximum_missing_minutes": max(
                    (gap.missing_minutes for gap in dataset.gaps),
                    default=0,
                ),
            },
            "execution_model": {
                "entry": "next_bar_open_adverse_slippage_capped_to_ohlc",
                "stop_gap": "adverse_bar_open_exit_slippage_capped_to_ohlc",
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
