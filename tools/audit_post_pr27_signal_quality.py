"""Read-only post-PR27 signal quality audit.

Parses existing session artifacts only. Does not import server.py, does not run
the pipeline, does not call SignalEngineV4, and does not dispatch anything.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


GENERATED_REASONS = {"scalper_generated", "swing_generated"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _signal_engine(snapshot_row: dict[str, Any]) -> dict[str, Any]:
    snapshot = snapshot_row.get("snapshot")
    if not isinstance(snapshot, dict):
        return {}
    stage_outputs = snapshot.get("stage_outputs")
    if not isinstance(stage_outputs, dict):
        return {}
    signal_engine = stage_outputs.get("signal_engine")
    return signal_engine if isinstance(signal_engine, dict) else {}


def _snapshot_payload(snapshot_row: dict[str, Any]) -> dict[str, Any]:
    snapshot = snapshot_row.get("snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _shadow_unlocks(signal_engine: dict[str, Any]) -> bool:
    shadow = signal_engine.get("last_valid_entry_shadow")
    if not isinstance(shadow, dict):
        return False
    return bool(
        shadow.get("valid_entry_ab_shadow_would_unlock")
        or shadow.get("valid_entry_shadow_without_mitigation_v1")
        or shadow.get("valid_entry_ab_delta") == "shadow_would_unlock"
    )


def _reason(signal_engine: dict[str, Any]) -> str:
    build_reason = signal_engine.get("last_build_signal_reason")
    valid_reason = signal_engine.get("last_valid_entry_reason")
    if build_reason in GENERATED_REASONS:
        return str(build_reason)
    return str(valid_reason or build_reason or "unknown")


def collect_quality(session_dir: Path) -> dict[str, Any]:
    session_dir = Path(session_dir)
    snapshots = _read_jsonl(session_dir / "signal_engine_full_path_snapshots.jsonl")
    decisions = _read_jsonl(session_dir / "pipeline_decisions.jsonl")
    dispatch = _read_jsonl(session_dir / "dispatch_events.jsonl")
    telegram = _read_jsonl(session_dir / "telegram_events.jsonl")

    build_reasons: Counter = Counter()
    valid_reasons: Counter = Counter()
    terminal_reasons: Counter = Counter()
    missing_fields: Counter = Counter()
    decision_reasons: Counter = Counter()

    real_outputs: list[dict[str, Any]] = []
    shadow_unlocks: list[dict[str, Any]] = []

    for row in snapshots:
        signal_engine = _signal_engine(row)
        snapshot = _snapshot_payload(row)

        build_reason = signal_engine.get("last_build_signal_reason")
        valid_reason = signal_engine.get("last_valid_entry_reason")
        signal_is_none = signal_engine.get("signal_is_none")

        if build_reason:
            build_reasons[str(build_reason)] += 1
        if valid_reason:
            valid_reasons[str(valid_reason)] += 1

        reason = _reason(signal_engine)
        terminal_reasons[reason] += 1

        for field in snapshot.get("missing_fields") or []:
            missing_fields[str(field)] += 1

        if build_reason in GENERATED_REASONS or signal_is_none is False:
            real_outputs.append(
                {
                    "decision_id": snapshot.get("decision_id"),
                    "timestamp": snapshot.get("timestamp"),
                    "reason": build_reason,
                    "price": snapshot.get("price"),
                    "missing_fields": snapshot.get("missing_fields") or [],
                }
            )

        if _shadow_unlocks(signal_engine):
            shadow_unlocks.append(
                {
                    "decision_id": snapshot.get("decision_id"),
                    "timestamp": snapshot.get("timestamp"),
                    "terminal_reason": reason,
                    "missing_fields": snapshot.get("missing_fields") or [],
                }
            )

    for row in decisions:
        decision_reasons[str(row.get("reason") or "unknown")] += 1

    return {
        "session_dir": str(session_dir),
        "metrics": {
            "total_snapshots": len(snapshots),
            "pipeline_decisions": len(decisions),
            "real_generated_signals": len(real_outputs),
            "shadow_unlocks": len(shadow_unlocks),
            "dispatch_events": len(dispatch),
            "telegram_events": len(telegram),
        },
        "reason_counts": {
            "build_signal": build_reasons.most_common(),
            "valid_entry": valid_reasons.most_common(),
            "terminal": terminal_reasons.most_common(),
            "pipeline_decisions": decision_reasons.most_common(),
            "missing_fields": missing_fields.most_common(),
        },
        "samples": {
            "real_outputs": real_outputs[:25],
            "shadow_unlocks": shadow_unlocks[:25],
        },
        "classification": {
            "safety": "PASS" if not dispatch and not telegram else "FAIL",
            "signal_quality_review": "REQUIRED" if real_outputs else "NO_REAL_OUTPUTS",
            "shadow_unlock_review": "REQUIRED" if shadow_unlocks else "NO_SHADOW_UNLOCKS",
            "operational_authorization": "NO_GO",
        },
        "interpretation_guards": [
            "real_generated_signals are internal SignalEngine outputs, not orders",
            "shadow_unlocks are research counters, not V2 activation approval",
            "dispatch_events and telegram_events must remain zero for this audit",
            "this tool is read-only and does not run the pipeline",
        ],
    }


def _table(items: list[tuple[Any, Any]]) -> list[str]:
    if not items:
        return ["| none | 0 |"]
    return [f"| {reason} | {count} |" for reason, count in items]


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Post-PR27 Signal Quality Audit",
        "",
        "## Source",
        "",
        f"- Session dir: `{report['session_dir']}`",
        "- Mode: read-only artifact parser",
        "",
        "## Metrics",
        "",
    ]
    for key, value in report["metrics"].items():
        lines.append(f"- `{key}`: {value}")

    for title, key in [
        ("Build Signal Reasons", "build_signal"),
        ("Valid Entry Reasons", "valid_entry"),
        ("Terminal Reasons", "terminal"),
        ("Pipeline Decision Reasons", "pipeline_decisions"),
        ("Missing Fields", "missing_fields"),
    ]:
        lines.extend(["", f"## {title}", "", "| reason | count |", "| --- | ---: |"])
        lines.extend(_table(report["reason_counts"][key]))

    lines.extend(["", "## Real Output Samples", ""])
    if report["samples"]["real_outputs"]:
        for item in report["samples"]["real_outputs"]:
            lines.append(f"- `{item.get('decision_id')}` reason=`{item.get('reason')}` price=`{item.get('price')}` missing={item.get('missing_fields')}")
    else:
        lines.append("- none")

    lines.extend(["", "## Shadow Unlock Samples", ""])
    if report["samples"]["shadow_unlocks"]:
        for item in report["samples"]["shadow_unlocks"]:
            lines.append(f"- `{item.get('decision_id')}` terminal_reason=`{item.get('terminal_reason')}` missing={item.get('missing_fields')}")
    else:
        lines.append("- none")

    lines.extend(["", "## Classification", ""])
    for key, value in report["classification"].items():
        lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Interpretation Guards", ""])
    lines.extend(f"- {item}" for item in report["interpretation_guards"])
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = collect_quality(args.session_dir)
    payload = json.dumps(report, indent=2, ensure_ascii=False) if args.json else format_markdown(report)

    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
