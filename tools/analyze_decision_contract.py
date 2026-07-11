"""Offline diagnosis of BIUMOLO's recorded decision contract.

The analyzer reads existing session artifacts only.  It does not import or
invoke strategy, runtime, execution, dispatch, network, or delivery code.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DECISIONS_FILE = "pipeline_decisions.jsonl"
SNAPSHOTS_FILE = "signal_engine_full_path_snapshots.jsonl"
SUMMARY_FILE = "session_summary.json"
OUTCOME_HORIZON = 20
GENERATED_REASONS = {"scalper_generated", "swing_generated"}
STRUCTURED_FIELDS = (
    "terminal_stage",
    "terminal_reason",
    "terminal_subreason",
    "build_signal_reason",
    "valid_entry_reason",
    "ob_reason",
    "timing_reason",
)
_SIDE_RE = re.compile(r"\bside\s*=\s*(BUY|SELL)\b", re.IGNORECASE)


class SessionValidationError(ValueError):
    """A complete session cannot be safely diagnosed."""


def discover_sessions(sessions_root: Path) -> list[Path]:
    root = Path(sessions_root)
    if not root.is_dir():
        return []
    found: set[Path] = set()
    for filename in (DECISIONS_FILE, SNAPSHOTS_FILE, SUMMARY_FILE):
        found.update(path.parent for path in root.rglob(filename) if path.is_file())
    if any((root / name).exists() for name in (DECISIONS_FILE, SNAPSHOTS_FILE, SUMMARY_FILE)):
        found.add(root)
    return sorted(found, key=lambda path: str(path.relative_to(root)))


def _read_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
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


def _number(value: Any, label: str, line_number: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SessionValidationError(f"invalid_{label}:line_{line_number}")
    result = float(value)
    if not math.isfinite(result):
        raise SessionValidationError(f"invalid_{label}:line_{line_number}")
    return result


def _timestamp_key(value: Any, line_number: int) -> float:
    if isinstance(value, bool):
        raise SessionValidationError(f"invalid_snapshot.timestamp:line_{line_number}")
    if isinstance(value, (int, float)):
        return _number(value, "snapshot.timestamp", line_number)
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


def _extract_explicit_side(detail: Any) -> str | None:
    if not isinstance(detail, str):
        return None
    match = _SIDE_RE.search(detail)
    return match.group(1).upper() if match else None


def derive_side(detail: Any, microstructure: dict[str, Any]) -> tuple[str | None, str | None]:
    explicit = _extract_explicit_side(detail)
    if explicit:
        return explicit, "decision_detail"

    ob = microstructure.get("ob")
    if isinstance(ob, dict):
        ob_side = str(ob.get("side") or ob.get("type") or "").lower()
        if ob_side in {"buy", "bullish", "up"}:
            return "BUY", "snapshot.microstructure.ob"
        if ob_side in {"sell", "bearish", "down"}:
            return "SELL", "snapshot.microstructure.ob"

    for field in ("displacement", "momentum"):
        value = str(microstructure.get(field) or "").lower()
        if value in {"buy", "bullish", "up"}:
            return "BUY", f"snapshot.microstructure.{field}"
        if value in {"sell", "bearish", "down"}:
            return "SELL", f"snapshot.microstructure.{field}"
    return None, None


def _is_structured(decision: dict[str, Any]) -> bool:
    return any(decision.get(field) not in (None, "") for field in STRUCTURED_FIELDS)


def _first_blocking_reason(decision: dict[str, Any]) -> str | None:
    terminal_reason = decision.get("terminal_reason")
    terminal_subreason = decision.get("terminal_subreason")
    if terminal_reason == "ok":
        return None
    return str(terminal_subreason or terminal_reason) if terminal_subreason or terminal_reason else None


def _active_filters(decision: dict[str, Any], micro: dict[str, Any]) -> list[str]:
    filters: set[str] = set()

    if not micro.get("displacement"):
        filters.add("missing_displacement")
    if not micro.get("momentum"):
        filters.add("missing_momentum")
    if micro.get("fake_displacement") is True:
        filters.add("fake_displacement_true")
    if micro.get("mitigation_light") is True:
        filters.add("mitigation_light_true")
    if micro.get("inducement") == "fake":
        filters.add("inducement_fake")

    valid_reason = decision.get("valid_entry_reason")
    if valid_reason not in (None, "", "entry_filters_passed"):
        filters.add(str(valid_reason))
    ob_reason = decision.get("ob_reason")
    if ob_reason not in (None, "", "ok"):
        filters.add(str(ob_reason))
    timing_reason = decision.get("timing_reason")
    if timing_reason not in (None, "", "ok"):
        filters.add(str(timing_reason))

    build_reason = decision.get("build_signal_reason")
    if build_reason not in (None, "", *GENERATED_REASONS, "valid_entry_failed", "timing_invalid"):
        filters.add(str(build_reason))

    first_block = _first_blocking_reason(decision)
    if first_block:
        filters.add(first_block)
    return sorted(filters)


def _read_decisions(path: Path) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for _line_number, row in _read_jsonl(path):
        decisions.append(
            {
                **{field: row.get(field) for field in STRUCTURED_FIELDS},
                "detail": row.get("detail"),
                "allowed": row.get("allowed"),
            }
        )
    return decisions


def _read_snapshots(path: Path, maximum_records: int) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    previous_key: float | None = None
    for line_number, row in _read_jsonl(path):
        if len(snapshots) >= maximum_records:
            raise SessionValidationError(
                "record_count_mismatch:snapshots_have_more_records_than_decisions"
            )
        snapshot = row.get("snapshot")
        if not isinstance(snapshot, dict):
            raise SessionValidationError(f"missing_snapshot:line_{line_number}")
        for field in ("timestamp", "price", "last_candle"):
            if field not in snapshot or snapshot[field] is None:
                raise SessionValidationError(f"missing_snapshot.{field}:line_{line_number}")
        timestamp = snapshot["timestamp"]
        timestamp_key = _timestamp_key(timestamp, line_number)
        if previous_key is not None and timestamp_key <= previous_key:
            raise SessionValidationError(
                f"snapshot_timestamps_not_strictly_increasing:line_{line_number}"
            )
        previous_key = timestamp_key

        candle = snapshot["last_candle"]
        if not isinstance(candle, dict):
            raise SessionValidationError(f"invalid_snapshot.last_candle:line_{line_number}")
        compact_candle = {
            field: _number(candle.get(field), f"last_candle.{field}", line_number)
            for field in ("high", "low", "close")
        }
        micro = snapshot.get("microstructure")
        snapshots.append(
            {
                "timestamp": timestamp,
                "price": _number(snapshot["price"], "snapshot.price", line_number),
                "last_candle": compact_candle,
                "microstructure": micro if isinstance(micro, dict) else {},
            }
        )
    return snapshots


def _load_summary(session_dir: Path) -> tuple[bool, dict[str, Any]]:
    path = session_dir / SUMMARY_FILE
    if not path.is_file():
        return False, {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeError, OSError) as exc:
        raise SessionValidationError(f"invalid_session_summary:{exc}") from exc
    if not isinstance(value, dict):
        raise SessionValidationError("invalid_session_summary:not_object")
    return True, value


def _outcome(
    snapshots: list[dict[str, Any]], index: int, side: str | None
) -> dict[str, Any]:
    target = index + OUTCOME_HORIZON
    if target >= len(snapshots):
        return {
            "horizon": OUTCOME_HORIZON,
            "status": "insufficient_future_data",
            "future_close": None,
            "future_return": None,
            "MFE": None,
            "MAE": None,
        }
    if side not in {"BUY", "SELL"}:
        return {
            "horizon": OUTCOME_HORIZON,
            "status": "side_unavailable",
            "future_close": snapshots[target]["last_candle"]["close"],
            "future_return": None,
            "MFE": None,
            "MAE": None,
        }

    price = snapshots[index]["price"]
    if price == 0:
        return {
            "horizon": OUTCOME_HORIZON,
            "status": "zero_decision_price",
            "future_close": snapshots[target]["last_candle"]["close"],
            "future_return": None,
            "MFE": None,
            "MAE": None,
        }
    future = snapshots[index + 1 : target + 1]
    close = snapshots[target]["last_candle"]["close"]
    raw_return = (close - price) / price
    if side == "BUY":
        signed_return = raw_return
        mfe = (max(row["last_candle"]["high"] for row in future) - price) / price
        mae = (min(row["last_candle"]["low"] for row in future) - price) / price
    else:
        signed_return = -raw_return
        mfe = (price - min(row["last_candle"]["low"] for row in future)) / price
        mae = (price - max(row["last_candle"]["high"] for row in future)) / price
    return {
        "horizon": OUTCOME_HORIZON,
        "status": "complete",
        "future_close": close,
        "future_return": signed_return,
        "MFE": mfe,
        "MAE": mae,
    }


def analyze_session(session_dir: Path) -> dict[str, Any]:
    session_dir = Path(session_dir)
    decisions_path = session_dir / DECISIONS_FILE
    snapshots_path = session_dir / SNAPSHOTS_FILE
    missing = [
        name
        for name, path in ((DECISIONS_FILE, decisions_path), (SNAPSHOTS_FILE, snapshots_path))
        if not path.is_file()
    ]
    if missing:
        raise SessionValidationError("missing_required_files:" + ",".join(missing))

    decisions = _read_decisions(decisions_path)
    snapshots = _read_snapshots(snapshots_path, len(decisions))
    if len(decisions) != len(snapshots):
        raise SessionValidationError(
            f"record_count_mismatch:decisions={len(decisions)}:snapshots={len(snapshots)}"
        )
    summary_present, summary = _load_summary(session_dir)

    records: list[dict[str, Any]] = []
    for ordinal, (decision, snapshot) in enumerate(zip(decisions, snapshots)):
        micro = snapshot["microstructure"]
        side, side_source = derive_side(decision.get("detail"), micro)
        records.append(
            {
                "session": session_dir.name,
                "ordinal": ordinal,
                "timestamp": snapshot["timestamp"],
                "structured": _is_structured(decision),
                **decision,
                "side": side,
                "side_source": side_source,
                "first_blocking_reason": _first_blocking_reason(decision),
                "active_filters": _active_filters(decision, micro),
                "outcome": _outcome(snapshots, ordinal, side),
            }
        )

    structured = [record for record in records if record["structured"]]
    derived = {
        "pipeline_decisions": len(records),
        "structured_decisions": len(structured),
        "build_signals": sum(
            record.get("build_signal_reason") in GENERATED_REASONS for record in structured
        ),
        "final_signals": sum(
            record.get("terminal_stage") == "final_signal"
            and record.get("terminal_reason") == "ok"
            for record in structured
        ),
        "execution_rejected": sum(
            record.get("terminal_reason") == "execution_rejected" for record in structured
        ),
    }
    reconciliation = {
        "summary_present": summary_present,
        "checks": [],
    }
    for summary_field, derived_field in (
        ("total_pipeline_executed", "pipeline_decisions"),
        ("total_build_signal_generated", "build_signals"),
        ("total_final_signals", "final_signals"),
        ("total_execution_rejected", "execution_rejected"),
    ):
        if summary.get(summary_field) is not None:
            reconciliation["checks"].append(
                {
                    "field": summary_field,
                    "summary": summary[summary_field],
                    "derived": derived[derived_field],
                    "matches": summary[summary_field] == derived[derived_field],
                }
            )
    return {
        "session_id": session_dir.name,
        "session_path": str(session_dir),
        "records": records,
        "derived": derived,
        "summary_reconciliation": reconciliation,
    }


def _percentage(count: int, total: int) -> float:
    return (count / total * 100.0) if total else 0.0


def build_funnel(records: list[dict[str, Any]]) -> dict[str, Any]:
    predicates = [
        ("pipeline_decisions", lambda row: True),
        ("ob_valid", lambda row: row.get("ob_reason") == "ok"),
        ("timing_valid", lambda row: row.get("timing_reason") == "ok"),
        ("valid_entry_passed", lambda row: row.get("valid_entry_reason") == "entry_filters_passed"),
        ("build_signal", lambda row: row.get("build_signal_reason") in GENERATED_REASONS),
        (
            "final_signal",
            lambda row: row.get("terminal_stage") == "final_signal"
            and row.get("terminal_reason") == "ok",
        ),
        ("execution", lambda row: row.get("allowed") is True),
    ]
    total = len(records)
    survivors = list(records)
    stages: list[dict[str, Any]] = []
    previous = total
    for index, (name, predicate) in enumerate(predicates):
        if index:
            survivors = [row for row in survivors if predicate(row)]
        count = len(survivors)
        drop = 0 if index == 0 else previous - count
        stages.append(
            {
                "stage": name,
                "count": count,
                "percentage": _percentage(count, total),
                "drop_from_previous": drop,
                "drop_from_previous_percentage": _percentage(drop, previous),
            }
        )
        previous = count
    transitions = stages[1:]
    highest = max(
        transitions,
        key=lambda stage: (stage["drop_from_previous_percentage"], stage["drop_from_previous"]),
        default=None,
    )
    return {
        "population": "structured_pipeline_decisions",
        "stages": stages,
        "highest_percentage_loss": highest,
    }


def _ranking(values: Iterable[Any], total: int) -> list[dict[str, Any]]:
    counts = Counter("<none>" if value in (None, "") else str(value) for value in values)
    return [
        {"rank": rank, "reason": reason, "count": count, "percentage": _percentage(count, total)}
        for rank, (reason, count) in enumerate(
            sorted(counts.items(), key=lambda item: (-item[1], item[0])), start=1
        )
    ]


def build_filter_analysis(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    filter_counts: Counter[str] = Counter()
    first_counts: Counter[str] = Counter()
    for record in records:
        filter_counts.update(record["active_filters"])
        first = record.get("first_blocking_reason")
        if first:
            first_counts[str(first)] += 1

    ranking = []
    for rank, (name, count) in enumerate(
        sorted(filter_counts.items(), key=lambda item: (-item[1], item[0])), start=1
    ):
        first_count = first_counts[name]
        ranking.append(
            {
                "rank": rank,
                "filter": name,
                "count": count,
                "percentage": _percentage(count, total),
                "first_blocking_count": first_count,
                "first_blocking_reason_frequency": _percentage(first_count, count),
            }
        )

    names = sorted(filter_counts)
    matrix = {name: {other: 0 for other in names} for name in names}
    for record in records:
        active = set(record["active_filters"])
        for left in active:
            for right in active:
                matrix[left][right] += 1

    overlaps = []
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            count = matrix[left][right]
            if count == 0:
                continue
            left_count = filter_counts[left]
            right_count = filter_counts[right]
            if left_count > right_count:
                dominant = left
            elif right_count > left_count:
                dominant = right
            else:
                dominant = "tie"
            overlaps.append(
                {
                    "left": left,
                    "right": right,
                    "count": count,
                    "percentage": _percentage(count, total),
                    "overlap_rate_of_smaller_filter": _percentage(
                        count, min(left_count, right_count)
                    ),
                    "dominant_filter": dominant,
                }
            )
    overlaps.sort(
        key=lambda item: (-item["count"], item["left"], item["right"])
    )
    top_two_filters = {item["filter"] for item in ranking[:2]}
    top_two_count = sum(item["count"] for item in ranking[:2])
    blocked = sum(record.get("first_blocking_reason") is not None for record in records)
    blocked_in_top_two = sum(
        record.get("first_blocking_reason") is not None
        and bool(top_two_filters.intersection(record["active_filters"]))
        for record in records
    )
    return {
        "ranking": ranking,
        "first_blocking_reason_ranking": _ranking(
            (record.get("first_blocking_reason") for record in records), total
        ),
        "top_two_filter_occurrences": top_two_count,
        "top_two_concentration_over_blocked_setups_percentage": _percentage(
            blocked_in_top_two, blocked
        ),
        "overlap_matrix": matrix,
        "overlap_ranking": overlaps,
    }


def _extreme_row(record: dict[str, Any], classification: str) -> dict[str, Any]:
    outcome = record["outcome"]
    return {
        "classification": classification,
        "session": record["session"],
        "timestamp": record["timestamp"],
        "side": record["side"],
        "side_source": record["side_source"],
        "blocking_reason": record.get("terminal_reason"),
        "blocking_subreason": record.get("terminal_subreason"),
        "future_return": outcome["future_return"],
        "MFE": outcome["MFE"],
        "MAE": outcome["MAE"],
        "horizon": OUTCOME_HORIZON,
    }


def build_outcome_extremes(records: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [record for record in records if record["outcome"]["status"] == "complete"]
    blocked = [
        record
        for record in complete
        if not (
            record.get("terminal_stage") == "final_signal"
            and record.get("terminal_reason") == "ok"
        )
    ]
    accepted = [
        record
        for record in complete
        if record.get("terminal_stage") == "final_signal"
        and record.get("terminal_reason") == "ok"
    ]
    blocked.sort(
        key=lambda record: (
            -record["outcome"]["MFE"],
            record["session"],
            str(record["timestamp"]),
        )
    )
    accepted.sort(
        key=lambda record: (
            record["outcome"]["future_return"],
            record["session"],
            str(record["timestamp"]),
        )
    )
    return {
        "horizon": OUTCOME_HORIZON,
        "return_unit": "fraction_of_decision_price",
        "blocked_ranking_metric": "MFE_descending",
        "accepted_ranking_metric": "signed_future_return_ascending",
        "blocked_complete_samples": len(blocked),
        "accepted_complete_samples": len(accepted),
        "top_20_blocked_strongest_favorable": [
            _extreme_row(record, "blocked_then_favorable") for record in blocked[:20]
        ],
        "top_20_accepted_worst_outcome": [
            _extreme_row(record, "accepted_then_adverse") for record in accepted[:20]
        ],
    }


def build_engineering_findings(
    funnel: dict[str, Any], filters: dict[str, Any], outcomes: dict[str, Any]
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    loss = funnel.get("highest_percentage_loss")
    if loss:
        findings.append(
            {
                "finding": "largest_structural_bottleneck",
                "evidence": (
                    f"The largest funnel loss occurs at {loss['stage']}: "
                    f"{loss['drop_from_previous']} candidates, "
                    f"{loss['drop_from_previous_percentage']:.2f}% of the previous stage."
                ),
            }
        )
    ranking = filters["ranking"]
    if ranking:
        names = ", ".join(item["filter"] for item in ranking[:2])
        findings.append(
            {
                "finding": "filter_concentration",
                "evidence": (
                    f"The two most frequent filters ({names}) account for "
                    f"{filters['top_two_concentration_over_blocked_setups_percentage']:.2f}% "
                    "of blocked setups by unique setup coverage."
                ),
            }
        )
    overlaps = filters["overlap_ranking"]
    if overlaps:
        overlap = overlaps[0]
        findings.append(
            {
                "finding": "highest_filter_overlap",
                "evidence": (
                    f"The most frequent overlap is {overlap['left']} with {overlap['right']}: "
                    f"{overlap['count']} co-occurrences; dominant filter by prevalence: "
                    f"{overlap['dominant_filter']}."
                ),
            }
        )
    findings.append(
        {
            "finding": "outcome_evaluable_samples",
            "evidence": (
                f"At +{OUTCOME_HORIZON}, {outcomes['blocked_complete_samples']} blocked setups "
                f"and {outcomes['accepted_complete_samples']} accepted setups have both a recorded "
                "direction and complete future data."
            ),
        }
    )
    return findings


def build_report(session_dirs: Iterable[Path]) -> dict[str, Any]:
    discovered = list(session_dirs)
    sessions = []
    invalid_sessions = []
    records: list[dict[str, Any]] = []
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
        records.extend(session["records"])
        sessions.append(
            {
                "session_id": session["session_id"],
                "session_path": session["session_path"],
                **session["derived"],
                "summary_reconciliation": session["summary_reconciliation"],
            }
        )

    structured = [record for record in records if record["structured"]]
    funnel = build_funnel(structured)
    filters = build_filter_analysis(structured)
    extremes = build_outcome_extremes(structured)
    return {
        "report_version": 1,
        "analysis": "offline_decision_contract_diagnosis",
        "sessions_discovered": len(discovered),
        "sessions_analyzed": len(sessions),
        "sessions_invalid": len(invalid_sessions),
        "sessions": sessions,
        "invalid_sessions": invalid_sessions,
        "coverage": {
            "pipeline_decisions_total": len(records),
            "structured_decisions": len(structured),
            "unstructured_decisions_excluded_from_contract": len(records) - len(structured),
            "structured_coverage_percentage": _percentage(len(structured), len(records)),
        },
        "decision_funnel": funnel,
        "terminal_reason_ranking": _ranking(
            (record.get("terminal_reason") for record in structured), len(structured)
        ),
        "terminal_subreason_ranking": _ranking(
            (record.get("terminal_subreason") for record in structured), len(structured)
        ),
        "filter_analysis": filters,
        "outcome_extremes": extremes,
        "engineering_findings": build_engineering_findings(funnel, filters, extremes),
        "safety": {
            "offline_only": True,
            "new_telemetry_added": False,
            "runtime_modified": False,
            "strategy_modified": False,
            "execution_modified": False,
        },
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def format_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    lines = [
        "# BIUMOLO Decision Contract Diagnosis",
        "",
        f"- Sessions discovered: {report['sessions_discovered']}",
        f"- Sessions analyzed: {report['sessions_analyzed']}",
        f"- Invalid sessions: {report['sessions_invalid']}",
        f"- Pipeline decisions in valid sessions: {coverage['pipeline_decisions_total']}",
        f"- Structured decisions diagnosed: {coverage['structured_decisions']}",
        f"- Structured coverage: {coverage['structured_coverage_percentage']:.2f}%",
        "",
        "## Decision funnel",
        "",
        "| Stage | Count | Percentage | Drop | Drop from previous |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for stage in report["decision_funnel"]["stages"]:
        lines.append(
            f"| {stage['stage']} | {stage['count']} | {stage['percentage']:.2f}% | "
            f"{stage['drop_from_previous']} | {stage['drop_from_previous_percentage']:.2f}% |"
        )

    for title, key in (
        ("Terminal reason ranking", "terminal_reason_ranking"),
        ("Terminal subreason ranking", "terminal_subreason_ranking"),
    ):
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| Rank | Reason | Count | Percentage of pipeline |",
                "| ---: | --- | ---: | ---: |",
            ]
        )
        for item in report[key]:
            lines.append(
                f"| {item['rank']} | {item['reason']} | {item['count']} | "
                f"{item['percentage']:.2f}% |"
            )

    lines.extend(
        [
            "",
            "## Filter concentration",
            "",
            "| Rank | Filter | Count | Percentage | First blocker count | First blocker frequency |",
            "| ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report["filter_analysis"]["ranking"]:
        lines.append(
            f"| {item['rank']} | {item['filter']} | {item['count']} | "
            f"{item['percentage']:.2f}% | {item['first_blocking_count']} | "
            f"{item['first_blocking_reason_frequency']:.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Filter overlap ranking",
            "",
            "| Filter A | Filter B | Together | Percentage | Smaller-filter overlap | Dominant |",
            "| --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in report["filter_analysis"]["overlap_ranking"]:
        lines.append(
            f"| {item['left']} | {item['right']} | {item['count']} | "
            f"{item['percentage']:.2f}% | {item['overlap_rate_of_smaller_filter']:.2f}% | "
            f"{item['dominant_filter']} |"
        )
    if not report["filter_analysis"]["overlap_ranking"]:
        lines.append("| none | none | 0 | 0.00% | 0.00% | none |")

    extremes = report["outcome_extremes"]
    for title, key in (
        ("Top 20 blocked setups with strongest favorable outcome", "top_20_blocked_strongest_favorable"),
        ("Top 20 accepted setups with worst subsequent outcome", "top_20_accepted_worst_outcome"),
    ):
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                f"Horizon: +{extremes['horizon']} candles.",
                "",
                "| Session | Timestamp | Side | Blocking reason | Blocking subreason | Future return | MFE | MAE |",
                "| --- | --- | --- | --- | --- | ---: | ---: | ---: |",
            ]
        )
        for item in extremes[key]:
            lines.append(
                f"| {item['session']} | {item['timestamp']} | {item['side']} | "
                f"{_fmt(item['blocking_reason'])} | {_fmt(item['blocking_subreason'])} | "
                f"{_fmt(item['future_return'])} | {_fmt(item['MFE'])} | {_fmt(item['MAE'])} |"
            )
        if not extremes[key]:
            lines.append("| none | - | - | - | - | null | null | null |")

    lines.extend(["", "## Engineering findings", ""])
    for finding in report["engineering_findings"]:
        lines.append(f"- **{finding['finding']}:** {finding['evidence']}")

    lines.extend(["", "## Invalid sessions", ""])
    if report["invalid_sessions"]:
        for session in report["invalid_sessions"]:
            lines.append(f"- `{session['session_id']}`: {session['reason']}")
    else:
        lines.append("- none")
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
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8-sig"
    )
    output_md.write_text(format_markdown(report), encoding="utf-8-sig")
    return output_json, output_md


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose BIUMOLO's recorded decision contract offline."
    )
    parser.add_argument("--sessions-root", default="logs/sessions")
    parser.add_argument(
        "--output-json", default="analysis_reports/decision_contract_diagnosis.json"
    )
    parser.add_argument(
        "--output-md", default="analysis_reports/decision_contract_diagnosis.md"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(discover_sessions(Path(args.sessions_root)))
    json_path, md_path = write_reports(
        report, Path(args.output_json), Path(args.output_md)
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Sessions discovered: {report['sessions_discovered']}")
    print(f"Sessions analyzed: {report['sessions_analyzed']}")
    print(f"Sessions invalid: {report['sessions_invalid']}")
    print(f"Structured decisions diagnosed: {report['coverage']['structured_decisions']}")
    loss = report["decision_funnel"]["highest_percentage_loss"]
    if loss:
        print(
            f"Largest funnel loss: {loss['stage']} "
            f"({loss['drop_from_previous_percentage']:.2f}%)"
        )
    for invalid in report["invalid_sessions"]:
        print(f"Invalid session {invalid['session_id']}: {invalid['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
