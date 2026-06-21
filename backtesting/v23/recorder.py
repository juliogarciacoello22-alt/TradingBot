from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from core.strategy_v23.models import Rejection, SignalDecision

from .fill_model import TradeResult


def _serialize(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, tuple):
        return list(value)
    return value


def _dictionary(record) -> dict:
    return {key: _serialize(value) for key, value in asdict(record).items()}


def write_results(
    output_dir: str | Path,
    *,
    manifest: dict,
    signals: list[SignalDecision],
    rejections: list[Rejection],
    trades: list[TradeResult],
    summary: dict,
    daily: list[dict],
    curve: list[dict],
) -> None:
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    (target / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (target / "daily.json").write_text(json.dumps(daily, indent=2), encoding="utf-8")
    (target / "equity_curve.json").write_text(json.dumps(curve, indent=2), encoding="utf-8")
    (target / "rejections.json").write_text(
        json.dumps([_dictionary(record) for record in rejections], indent=2), encoding="utf-8"
    )
    _write_csv(target / "signals.csv", [_dictionary(record) for record in signals])
    _write_csv(target / "trades.csv", [_dictionary(record) for record in trades])


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value) if isinstance(value, (dict, list)) else value for key, value in row.items()})

