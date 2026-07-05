"""Read-only SHADOW vs REAL audit metrics for post-PR19 session artifacts.

This script parses already-recorded audit files. It does not import the live
pipeline, instantiate trading engines, send signals, or write files unless an
explicit --output path is provided.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


GENERATED_REASONS = {"scalper_generated", "swing_generated"}
SESSION_FILES = {
    "snapshots": "signal_engine_full_path_snapshots.jsonl",
    "pipeline_decisions": "pipeline_decisions.jsonl",
    "signal_candidates": "signal_candidates.jsonl",
    "signals_enriched": "signals_enriched.jsonl",
    "dispatch_events": "dispatch_events.jsonl",
    "telegram_events": "telegram_events.jsonl",
}


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    data = path.read_bytes()
    if not data:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _read_text(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _stage_signal_engine(record: dict[str, Any]) -> dict[str, Any]:
    snapshot = record.get("snapshot")
    if not isinstance(snapshot, dict):
        return {}
    stage_outputs = snapshot.get("stage_outputs")
    if not isinstance(stage_outputs, dict):
        return {}
    signal_engine = stage_outputs.get("signal_engine")
    return signal_engine if isinstance(signal_engine, dict) else {}


def _shadow_unlocks(signal_engine: dict[str, Any]) -> bool:
    shadow = signal_engine.get("last_valid_entry_shadow")
    if not isinstance(shadow, dict):
        return False
    return bool(
        shadow.get("valid_entry_ab_shadow_would_unlock")
        or shadow.get("valid_entry_shadow_without_mitigation_v1")
        or shadow.get("valid_entry_ab_delta") == "shadow_would_unlock"
    )


def _snapshot_block_reason(signal_engine: dict[str, Any]) -> str:
    build_reason = signal_engine.get("last_build_signal_reason")
    valid_reason = signal_engine.get("last_valid_entry_reason")
    if build_reason in GENERATED_REASONS:
        return ""
    return str(valid_reason or build_reason or "unknown")


def _count_reason(rows: Iterable[dict[str, Any]], *keys: str) -> Counter:
    counts: Counter = Counter()
    for row in rows:
        for key in keys:
            value = row.get(key)
            if value:
                counts[str(value)] += 1
                break
    return counts


def collect_metrics(session_dir: Path) -> dict[str, Any]:
    session_dir = Path(session_dir)
    snapshots = read_jsonl(session_dir / SESSION_FILES["snapshots"])
    pipeline_decisions = read_jsonl(session_dir / SESSION_FILES["pipeline_decisions"])
    signal_candidates = read_jsonl(session_dir / SESSION_FILES["signal_candidates"])
    signals_enriched = read_jsonl(session_dir / SESSION_FILES["signals_enriched"])
    dispatch_events = read_jsonl(session_dir / SESSION_FILES["dispatch_events"])
    telegram_events = read_jsonl(session_dir / SESSION_FILES["telegram_events"])

    snapshot_reasons: Counter = Counter()
    valid_entry_reasons: Counter = Counter()
    build_signal_reasons: Counter = Counter()
    shadow_unlocks = 0
    shadow_generated = 0
    real_generated_from_snapshots = 0
    shadow_signal_real_block_cases = 0

    for record in snapshots:
        signal_engine = _stage_signal_engine(record)
        build_reason = signal_engine.get("last_build_signal_reason")
        valid_reason = signal_engine.get("last_valid_entry_reason")
        signal_is_none = signal_engine.get("signal_is_none")

        if build_reason:
            build_signal_reasons[str(build_reason)] += 1
        if valid_reason:
            valid_entry_reasons[str(valid_reason)] += 1

        if _shadow_unlocks(signal_engine):
            shadow_unlocks += 1
            shadow_generated += 1
            if signal_is_none is True:
                shadow_signal_real_block_cases += 1

        if build_reason in GENERATED_REASONS or signal_is_none is False:
            real_generated_from_snapshots += 1

        block_reason = _snapshot_block_reason(signal_engine)
        if block_reason:
            snapshot_reasons[block_reason] += 1

    real_generated = max(real_generated_from_snapshots, len(signals_enriched), len(signal_candidates))
    dispatch_allowed = sum(1 for row in dispatch_events if row.get("allowed") is True)
    dispatch_blocked = sum(1 for row in dispatch_events if row.get("allowed") is False)
    telegram_sent = sum(1 for row in telegram_events if row.get("sent") is True)
    telegram_failed = sum(1 for row in telegram_events if row.get("sent") is False)
    real_signal_not_dispatched_cases = max(real_generated - dispatch_allowed, 0)

    return {
        "session_dir": str(session_dir),
        "source_files": {
            name: str(session_dir / filename) for name, filename in SESSION_FILES.items()
        },
        "metrics": {
            "total_snapshots": len(snapshots),
            "total_build_signal_results": sum(build_signal_reasons.values()),
            "total_valid_entry_blocks": sum(
                count for reason, count in valid_entry_reasons.items() if reason != "entry_filters_passed"
            ),
            "mitigation_light_true": valid_entry_reasons.get("mitigation_light_true", 0),
            "v2_shadow_would_unlock": shadow_unlocks,
            "shadow_generated_signals": shadow_generated,
            "real_generated_signals": real_generated,
            "pipeline_decisions": len(pipeline_decisions),
            "dispatch_events": len(dispatch_events),
            "dispatch_allowed": dispatch_allowed,
            "dispatch_blocked": dispatch_blocked,
            "telegram_events": len(telegram_events),
            "telegram_sent": telegram_sent,
            "telegram_failed": telegram_failed,
            "shadow_signal_real_block_cases": shadow_signal_real_block_cases,
            "real_signal_not_dispatched_cases": real_signal_not_dispatched_cases,
        },
        "reason_counts": {
            "build_signal": build_signal_reasons.most_common(),
            "valid_entry": valid_entry_reasons.most_common(),
            "snapshot_blocks": snapshot_reasons.most_common(),
            "pipeline_no_trade": _count_reason(
                (row for row in pipeline_decisions if row.get("final_decision") == "NO_TRADE"),
                "final_reason",
                "reason",
            ).most_common(),
            "dispatch_blocks": _count_reason(
                (row for row in dispatch_events if row.get("allowed") is False),
                "reason",
                "dispatch_status",
            ).most_common(),
        },
        "interpretation_guards": [
            "shadow_generated_signals are research/audit signals, not trade authorization",
            "real_generated_signals are signal-engine outputs, not necessarily dispatched orders",
            "v2_shadow_would_unlock is a research counter, not approval for V2, Sim101, or Live",
            "dispatch_allowed and telegram_sent are the closest available evidence of downstream delivery",
        ],
    }


def format_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    reason_counts = report["reason_counts"]

    def rows(items: list[list[Any]] | list[tuple[Any, Any]]) -> list[str]:
        if not items:
            return ["| none | 0 |"]
        return [f"| {reason} | {count} |" for reason, count in items]

    lines = [
        "# SHADOW vs REAL Post-PR19 Audit Metrics",
        "",
        "## Source",
        "",
        f"- Session dir: `{report['session_dir']}`",
        "- Mode: read-only artifact parser",
        "",
        "## Metrics",
        "",
    ]
    for key, value in metrics.items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(
        [
            "",
            "## Build Signal Reasons",
            "",
            "| reason | count |",
            "| --- | ---: |",
            *rows(reason_counts["build_signal"]),
            "",
            "## Valid Entry Reasons",
            "",
            "| reason | count |",
            "| --- | ---: |",
            *rows(reason_counts["valid_entry"]),
            "",
            "## Snapshot Blocks",
            "",
            "| reason | count |",
            "| --- | ---: |",
            *rows(reason_counts["snapshot_blocks"]),
            "",
            "## Dispatch Blocks",
            "",
            "| reason | count |",
            "| --- | ---: |",
            *rows(reason_counts["dispatch_blocks"]),
            "",
            "## Interpretation Guards",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report["interpretation_guards"])
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path, help="Existing logs/sessions/<id> directory")
    parser.add_argument("--output", type=Path, help="Optional markdown output path")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown")
    args = parser.parse_args(argv)

    report = collect_metrics(args.session_dir)
    if args.json:
        payload = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        payload = format_markdown(report)

    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
