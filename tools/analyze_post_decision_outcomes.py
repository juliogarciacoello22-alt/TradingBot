"""Offline post-decision outcome analysis for BIUMOLO session artifacts.

This module only reads existing JSONL files and writes local reports.  It does
not import or invoke any trading, execution, dispatch, or runtime component.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DECISIONS_FILE = "pipeline_decisions.jsonl"
SNAPSHOTS_FILE = "signal_engine_full_path_snapshots.jsonl"
HORIZONS = (5, 10, 20, 50)
GROUP_FIELDS = (
    "terminal_stage",
    "terminal_reason",
    "terminal_subreason",
    "build_signal_reason",
    "side",
)
DECISION_FIELDS = (
    "terminal_stage",
    "terminal_reason",
    "terminal_subreason",
    "build_signal_reason",
    "valid_entry_reason",
    "ob_reason",
    "timing_reason",
    "detail",
)
_SIDE_RE = re.compile(r"\bside\s*=\s*(BUY|SELL)\b", re.IGNORECASE)


class SessionValidationError(ValueError):
    """Raised when a session cannot be analyzed as one complete unit."""


def extract_side(detail: Any) -> str | None:
    """Extract an explicit BUY/SELL marker from a decision detail string."""

    if not isinstance(detail, str):
        return None
    match = _SIDE_RE.search(detail)
    return match.group(1).upper() if match else None


def discover_sessions(sessions_root: Path) -> list[Path]:
    """Discover directories containing either member of the required pair."""

    root = Path(sessions_root)
    if not root.exists() or not root.is_dir():
        return []

    found: set[Path] = set()
    if (root / DECISIONS_FILE).exists() or (root / SNAPSHOTS_FILE).exists():
        found.add(root)
    for filename in (DECISIONS_FILE, SNAPSHOTS_FILE):
        found.update(path.parent for path in root.rglob(filename) if path.is_file())
    return sorted(found, key=lambda path: str(path.relative_to(root)))


def _jsonl_rows(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8-sig", errors="strict") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise SessionValidationError(
                    f"invalid_json:{path.name}:line_{line_number}:{exc.msg}"
                ) from exc
            if not isinstance(row, dict):
                raise SessionValidationError(
                    f"record_not_object:{path.name}:line_{line_number}"
                )
            yield line_number, row


def _finite_number(value: Any, label: str, line_number: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SessionValidationError(f"invalid_{label}:line_{line_number}")
    number = float(value)
    if not math.isfinite(number):
        raise SessionValidationError(f"invalid_{label}:line_{line_number}")
    return number


def _timestamp_sort_key(value: Any, line_number: int) -> float:
    if isinstance(value, bool):
        raise SessionValidationError(f"invalid_snapshot.timestamp:line_{line_number}")
    if isinstance(value, (int, float)):
        return _finite_number(value, "snapshot.timestamp", line_number)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise SessionValidationError(
                    f"invalid_snapshot.timestamp:line_{line_number}"
                ) from exc
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
    raise SessionValidationError(f"invalid_snapshot.timestamp:line_{line_number}")


def _read_decisions(path: Path) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for _line_number, row in _jsonl_rows(path):
        decision = {field: row.get(field) for field in DECISION_FIELDS}
        decision["side"] = extract_side(decision["detail"])
        decisions.append(decision)
    return decisions


def _read_snapshots(path: Path, maximum_records: int) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    previous_timestamp_key: float | None = None

    for line_number, row in _jsonl_rows(path):
        if len(snapshots) >= maximum_records:
            raise SessionValidationError(
                "record_count_mismatch:signal_engine_full_path_snapshots.jsonl_"
                "has_more_records_than_pipeline_decisions.jsonl"
            )

        payload = row.get("snapshot")
        if not isinstance(payload, dict):
            raise SessionValidationError(f"missing_snapshot:line_{line_number}")
        for field in ("timestamp", "price", "last_candle"):
            if field not in payload or payload[field] is None:
                raise SessionValidationError(
                    f"missing_snapshot.{field}:line_{line_number}"
                )

        timestamp = payload["timestamp"]
        timestamp_key = _timestamp_sort_key(timestamp, line_number)
        price = _finite_number(payload["price"], "snapshot.price", line_number)
        if previous_timestamp_key is not None and timestamp_key <= previous_timestamp_key:
            raise SessionValidationError(
                f"snapshot_timestamps_not_strictly_increasing:line_{line_number}"
            )
        previous_timestamp_key = timestamp_key

        candle = payload["last_candle"]
        if not isinstance(candle, dict):
            raise SessionValidationError(
                f"invalid_snapshot.last_candle:line_{line_number}"
            )
        compact_candle = {
            field: _finite_number(candle.get(field), f"last_candle.{field}", line_number)
            for field in ("high", "low", "close")
        }
        snapshots.append(
            {
                "decision_id": payload.get("decision_id"),
                "timestamp": timestamp,
                "price": price,
                "last_candle": compact_candle,
                "instrument": payload.get("instrument", candle.get("instrument")),
                "barType": payload.get("barType", candle.get("barType")),
                "barSize": payload.get("barSize", candle.get("barSize")),
            }
        )
    return snapshots


def _horizon_result(
    snapshots: list[dict[str, Any]], index: int, horizon: int, side: str | None
) -> dict[str, Any]:
    target_index = index + horizon
    if target_index >= len(snapshots):
        return {
            "close": None,
            "raw_return": None,
            "signed_return": None,
            "MFE": None,
            "MAE": None,
            "status": "insufficient_future_data",
        }

    price = snapshots[index]["price"]
    future = snapshots[index + 1 : target_index + 1]
    close = snapshots[target_index]["last_candle"]["close"]
    raw_return = (close - price) / price if price != 0 else None

    signed_return: float | None = None
    mfe: float | None = None
    mae: float | None = None
    if side == "BUY" and price != 0:
        signed_return = raw_return
        mfe = (max(item["last_candle"]["high"] for item in future) - price) / price
        mae = (min(item["last_candle"]["low"] for item in future) - price) / price
    elif side == "SELL" and price != 0:
        signed_return = -raw_return if raw_return is not None else None
        mfe = (price - min(item["last_candle"]["low"] for item in future)) / price
        mae = (price - max(item["last_candle"]["high"] for item in future)) / price

    return {
        "close": close,
        "raw_return": raw_return,
        "signed_return": signed_return,
        "MFE": mfe,
        "MAE": mae,
        "status": "complete",
    }


def analyze_session(session_dir: Path) -> dict[str, Any]:
    """Validate and analyze a session atomically, using ordinal alignment only."""

    session_dir = Path(session_dir)
    decisions_path = session_dir / DECISIONS_FILE
    snapshots_path = session_dir / SNAPSHOTS_FILE
    missing = [
        name
        for name, path in (
            (DECISIONS_FILE, decisions_path),
            (SNAPSHOTS_FILE, snapshots_path),
        )
        if not path.is_file()
    ]
    if missing:
        raise SessionValidationError("missing_required_files:" + ",".join(missing))

    decisions = _read_decisions(decisions_path)
    snapshots = _read_snapshots(snapshots_path, len(decisions))
    if len(decisions) != len(snapshots):
        raise SessionValidationError(
            f"record_count_mismatch:pipeline_decisions={len(decisions)}:snapshots={len(snapshots)}"
        )

    outcomes: list[dict[str, Any]] = []
    for index, (decision, snapshot) in enumerate(zip(decisions, snapshots)):
        outcome = {
            "ordinal": index,
            **decision,
            "decision_id": snapshot["decision_id"],
            "timestamp": snapshot["timestamp"],
            "price": snapshot["price"],
            "last_candle": snapshot["last_candle"],
            "instrument": snapshot["instrument"],
            "barType": snapshot["barType"],
            "barSize": snapshot["barSize"],
            "horizons": {
                str(horizon): _horizon_result(snapshots, index, horizon, decision["side"])
                for horizon in HORIZONS
            },
        }
        outcomes.append(outcome)

    return {
        "session_id": session_dir.name,
        "session_path": str(session_dir),
        "record_count": len(outcomes),
        "outcomes": outcomes,
    }


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _aggregate_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    horizon_stats: dict[str, Any] = {}
    for horizon in HORIZONS:
        values = [row["horizons"][str(horizon)] for row in rows]
        complete = [value for value in values if value["status"] == "complete"]
        signed = [value["signed_return"] for value in complete if value["signed_return"] is not None]
        mfes = [value["MFE"] for value in complete if value["MFE"] is not None]
        maes = [value["MAE"] for value in complete if value["MAE"] is not None]
        horizon_stats[str(horizon)] = {
            "count": len(values),
            "complete_samples": len(complete),
            "insufficient_samples": len(values) - len(complete),
            "mean": _mean(signed),
            "median": _median(signed),
            "MFE": _mean(mfes),
            "MAE": _mean(maes),
            "favorable_close_rate": (
                sum(value > 0 for value in signed) / len(signed) if signed else None
            ),
        }
    return horizon_stats


def build_aggregates(outcomes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    aggregates: dict[str, list[dict[str, Any]]] = {}
    for field in GROUP_FIELDS:
        groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for outcome in outcomes:
            groups[outcome.get(field)].append(outcome)
        aggregates[field] = [
            {
                "value": value,
                "count": len(rows),
                "horizons": _aggregate_group(rows),
            }
            for value, rows in sorted(
                groups.items(), key=lambda item: (item[0] is None, str(item[0]))
            )
        ]
    return aggregates


def build_report(session_dirs: Iterable[Path]) -> dict[str, Any]:
    sessions: list[dict[str, Any]] = []
    invalid_sessions: list[dict[str, str]] = []
    all_outcomes: list[dict[str, Any]] = []
    discovered = list(session_dirs)

    for session_dir in discovered:
        try:
            session = analyze_session(session_dir)
        except (SessionValidationError, UnicodeError, OSError) as exc:
            invalid_sessions.append(
                {
                    "session_id": Path(session_dir).name,
                    "session_path": str(session_dir),
                    "reason": str(exc),
                }
            )
            continue
        sessions.append(
            {
                "session_id": session["session_id"],
                "session_path": session["session_path"],
                "record_count": session["record_count"],
            }
        )
        all_outcomes.extend(session["outcomes"])

    return {
        "report_version": 1,
        "analysis": "offline_post_decision_outcomes",
        "horizons": list(HORIZONS),
        "join": "ordinal_only",
        "return_unit": "fraction_of_decision_price",
        "sessions_discovered": len(discovered),
        "sessions_analyzed": len(sessions),
        "sessions_invalid": len(invalid_sessions),
        "sessions": sessions,
        "invalid_sessions": invalid_sessions,
        "outcomes": all_outcomes,
        "aggregates": build_aggregates(all_outcomes),
        "safety": {
            "offline_only": True,
            "runtime_modified": False,
            "trading_behavior_modified": False,
        },
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# BIUMOLO Offline Post-Decision Outcomes",
        "",
        f"- Sessions discovered: {report['sessions_discovered']}",
        f"- Sessions analyzed: {report['sessions_analyzed']}",
        f"- Invalid sessions: {report['sessions_invalid']}",
        f"- Decisions analyzed: {len(report['outcomes'])}",
        "- Join: ordinal only",
        "- Return unit: fraction of decision price",
        "",
        "## Session validation",
        "",
        "| Session | Status | Records / reason |",
        "| --- | --- | --- |",
    ]
    for session in report["sessions"]:
        lines.append(
            f"| {session['session_id']} | analyzed | {session['record_count']} |"
        )
    for session in report["invalid_sessions"]:
        reason = session["reason"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {session['session_id']} | invalid | {reason} |")
    if not report["sessions"] and not report["invalid_sessions"]:
        lines.append("| none | - | - |")

    for field in GROUP_FIELDS:
        lines.extend(["", f"## Aggregate by `{field}`", ""])
        for group in report["aggregates"][field]:
            lines.extend(
                [
                    f"### {_fmt(group['value'])}",
                    "",
                    "| Horizon | Count | Complete | Insufficient | Mean | Median | MFE | MAE | Favorable close rate |",
                    "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for horizon in HORIZONS:
                stats = group["horizons"][str(horizon)]
                lines.append(
                    f"| {horizon} | {stats['count']} | {stats['complete_samples']} | "
                    f"{stats['insufficient_samples']} | {_fmt(stats['mean'])} | "
                    f"{_fmt(stats['median'])} | {_fmt(stats['MFE'])} | "
                    f"{_fmt(stats['MAE'])} | {_fmt(stats['favorable_close_rate'])} |"
                )
        if not report["aggregates"][field]:
            lines.extend(
                [
                    "| Horizon | Count | Complete | Insufficient | Mean | Median | MFE | MAE | Favorable close rate |",
                    "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                    "| - | 0 | 0 | 0 | null | null | null | null | null |",
                ]
            )
    lines.append("")
    return "\n".join(lines)


def write_reports(
    report: dict[str, Any], output_json: Path, output_md: Path
) -> tuple[Path, Path]:
    output_json = Path(output_json)
    output_md = Path(output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8-sig",
    )
    output_md.write_text(format_markdown(report), encoding="utf-8-sig")
    return output_json, output_md


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze post-decision outcomes from existing BIUMOLO sessions."
    )
    parser.add_argument("--sessions-root", default="logs/sessions")
    parser.add_argument(
        "--output-json", default="analysis_reports/post_decision_outcomes.json"
    )
    parser.add_argument(
        "--output-md", default="analysis_reports/post_decision_outcomes.md"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session_dirs = discover_sessions(Path(args.sessions_root))
    report = build_report(session_dirs)
    json_path, md_path = write_reports(
        report, Path(args.output_json), Path(args.output_md)
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Sessions discovered: {report['sessions_discovered']}")
    print(f"Sessions analyzed: {report['sessions_analyzed']}")
    print(f"Sessions invalid: {report['sessions_invalid']}")
    print(f"Decisions analyzed: {len(report['outcomes'])}")
    for invalid in report["invalid_sessions"]:
        print(f"Invalid session {invalid['session_id']}: {invalid['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
