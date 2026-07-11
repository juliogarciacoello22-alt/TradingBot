"""Build an offline, evidence-only scorecard for recorded decision filters.

The module consumes existing session artifacts.  It never imports runtime or
strategy components, reconstructs signals, or simulates trading.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DECISIONS_FILE = "pipeline_decisions.jsonl"
SNAPSHOTS_FILE = "signal_engine_full_path_snapshots.jsonl"
SUMMARY_FILE = "session_summary.json"
HORIZONS = (5, 10, 20, 50)
PRIMARY_HORIZON = 20
_SIDE_RE = re.compile(r"\bside\s*=\s*(BUY|SELL)\b", re.IGNORECASE)
_MISSING_PREFIX_RE = re.compile(r"^missing_(.+)$")
_MISSING_SUFFIX_RE = re.compile(r"^(.+)_missing$")
_BOOLEAN_SUFFIX_RE = re.compile(r"^(.+)_(true|false)$")


class SessionValidationError(ValueError):
    """A session cannot be analyzed atomically."""


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


def _reason_fields(row: dict[str, Any]) -> dict[str, str]:
    """Discover reason-bearing decision fields without a filter allowlist."""

    result = {}
    for key, value in row.items():
        if key == "terminal_subreason" or key.endswith("_reason"):
            if value not in (None, "") and not isinstance(value, (dict, list)):
                result[key] = str(value)
    return result


def _first_block(row: dict[str, Any]) -> str | None:
    terminal_reason = row.get("terminal_reason")
    if terminal_reason == "ok":
        return None
    value = row.get("terminal_subreason") or terminal_reason
    return str(value) if value not in (None, "") else None


def _is_structured(row: dict[str, Any]) -> bool:
    return bool(_reason_fields(row)) and row.get("terminal_reason") not in (None, "")


def _flatten_scalars(value: Any, prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_scalars(child, path))
    elif not isinstance(value, list):
        flattened[prefix] = value
    return flattened


def _read_decisions(path: Path) -> list[dict[str, Any]]:
    decisions = []
    for _line_number, row in _read_jsonl(path):
        decisions.append(
            {
                "terminal_stage": row.get("terminal_stage"),
                "terminal_reason": row.get("terminal_reason"),
                "terminal_subreason": row.get("terminal_subreason"),
                "detail": row.get("detail"),
                "allowed": row.get("allowed"),
                "reason_fields": _reason_fields(row),
                "structured": _is_structured(row),
            }
        )
    return decisions


def _read_snapshots(path: Path, maximum_records: int) -> list[dict[str, Any]]:
    snapshots = []
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
        key = _timestamp_key(timestamp, line_number)
        if previous_key is not None and key <= previous_key:
            raise SessionValidationError(
                f"snapshot_timestamps_not_strictly_increasing:line_{line_number}"
            )
        previous_key = key
        candle = snapshot["last_candle"]
        if not isinstance(candle, dict):
            raise SessionValidationError(f"invalid_snapshot.last_candle:line_{line_number}")
        compact_candle = {
            field: _number(candle.get(field), f"last_candle.{field}", line_number)
            for field in ("high", "low", "close")
        }
        micro = snapshot.get("microstructure")
        if not isinstance(micro, dict):
            micro = {}
        snapshots.append(
            {
                "timestamp": timestamp,
                "price": _number(snapshot["price"], "snapshot.price", line_number),
                "last_candle": compact_candle,
                "microstructure": micro,
                "features": _flatten_scalars(micro),
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


def _explicit_side(detail: Any) -> str | None:
    if not isinstance(detail, str):
        return None
    match = _SIDE_RE.search(detail)
    return match.group(1).upper() if match else None


def derive_side(detail: Any, micro: dict[str, Any]) -> tuple[str | None, str | None]:
    explicit = _explicit_side(detail)
    if explicit:
        return explicit, "decision_detail"
    ob = micro.get("ob")
    if isinstance(ob, dict):
        direction = str(ob.get("side") or ob.get("type") or "").lower()
        if direction in {"buy", "bullish", "up"}:
            return "BUY", "snapshot.microstructure.ob"
        if direction in {"sell", "bearish", "down"}:
            return "SELL", "snapshot.microstructure.ob"
    for field in ("displacement", "momentum"):
        direction = str(micro.get(field) or "").lower()
        if direction in {"buy", "bullish", "up"}:
            return "BUY", f"snapshot.microstructure.{field}"
        if direction in {"sell", "bearish", "down"}:
            return "SELL", f"snapshot.microstructure.{field}"
    return None, None


def _outcomes(
    snapshots: list[dict[str, Any]], index: int, side: str | None
) -> dict[str, dict[str, Any]]:
    results = {}
    for horizon in HORIZONS:
        target = index + horizon
        empty = {
            "close": None,
            "return": None,
            "MFE": None,
            "MAE": None,
        }
        if target >= len(snapshots):
            results[str(horizon)] = {
                **empty,
                "status": "insufficient_future_data",
            }
            continue
        close = snapshots[target]["last_candle"]["close"]
        if side not in {"BUY", "SELL"}:
            results[str(horizon)] = {
                **empty,
                "close": close,
                "status": "side_unavailable",
            }
            continue
        price = snapshots[index]["price"]
        if price == 0:
            results[str(horizon)] = {
                **empty,
                "close": close,
                "status": "zero_decision_price",
            }
            continue
        future = snapshots[index + 1 : target + 1]
        raw_return = (close - price) / price
        if side == "BUY":
            signed_return = raw_return
            mfe = (max(item["last_candle"]["high"] for item in future) - price) / price
            mae = (min(item["last_candle"]["low"] for item in future) - price) / price
        else:
            signed_return = -raw_return
            mfe = (price - min(item["last_candle"]["low"] for item in future)) / price
            mae = (price - max(item["last_candle"]["high"] for item in future)) / price
        results[str(horizon)] = {
            "close": close,
            "return": signed_return,
            "MFE": mfe,
            "MAE": mae,
            "status": "complete",
        }
    return results


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
    summary_present, _summary = _load_summary(session_dir)
    records = []
    for ordinal, (decision, snapshot) in enumerate(zip(decisions, snapshots)):
        side, side_source = derive_side(decision["detail"], snapshot["microstructure"])
        records.append(
            {
                "session_id": session_dir.name,
                "ordinal": ordinal,
                "timestamp": snapshot["timestamp"],
                **decision,
                "first_block": _first_block(
                    {
                        "terminal_reason": decision["terminal_reason"],
                        "terminal_subreason": decision["terminal_subreason"],
                    }
                ),
                "features": snapshot["features"],
                "side": side,
                "side_source": side_source,
                "outcomes": _outcomes(snapshots, ordinal, side),
            }
        )
    return {
        "session_id": session_dir.name,
        "session_path": str(session_dir),
        "record_count": len(records),
        "structured_count": sum(record["structured"] for record in records),
        "summary_present": summary_present,
        "records": records,
    }


def _reason_value_is_specific(record: dict[str, Any], field: str, value: str) -> bool:
    if field == "terminal_reason" and record.get("terminal_subreason"):
        return False
    if value == record.get("terminal_reason") and record.get("terminal_subreason"):
        return False
    return True


def discover_filter_names(records: list[dict[str, Any]]) -> list[str]:
    """Discover filters from observed blocking evidence, with no filter names in code."""

    accepted_pass_values: dict[str, set[str]] = {}
    for record in records:
        if record.get("first_block") is None:
            for field, value in record["reason_fields"].items():
                accepted_pass_values.setdefault(field, set()).add(value)

    filters = {record["first_block"] for record in records if record.get("first_block")}
    for record in records:
        if record.get("first_block") is None:
            continue
        for field, value in record["reason_fields"].items():
            if not _reason_value_is_specific(record, field, value):
                continue
            if value not in accepted_pass_values.get(field, set()):
                filters.add(value)
    return sorted(str(value) for value in filters if value not in (None, ""))


def _feature_matches_filter(filter_name: str, features: dict[str, Any]) -> bool:
    missing = _MISSING_PREFIX_RE.match(filter_name) or _MISSING_SUFFIX_RE.match(filter_name)
    boolean = _BOOLEAN_SUFFIX_RE.match(filter_name)
    if missing:
        feature_name = missing.group(1)
        return any(
            path.rsplit(".", 1)[-1] == feature_name and value in (None, False, "")
            for path, value in features.items()
        )
    if boolean:
        feature_name, expected_text = boolean.groups()
        expected = expected_text == "true"
        return any(
            path.rsplit(".", 1)[-1] == feature_name and value is expected
            for path, value in features.items()
        )
    return False


def annotate_filter_activity(
    records: list[dict[str, Any]], filter_names: Iterable[str]
) -> None:
    filters = set(filter_names)
    for record in records:
        active = {record["first_block"]} if record.get("first_block") else set()
        for field, value in record["reason_fields"].items():
            if value in filters and _reason_value_is_specific(record, field, value):
                active.add(value)
        for name in filters:
            if _feature_matches_filter(name, record["features"]):
                active.add(name)
        record["active_filters"] = sorted(active.intersection(filters))


def _percentage(count: int, total: int) -> float:
    return count / total * 100.0 if total else 0.0


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _horizon_metrics(records: list[dict[str, Any]], horizon: int) -> dict[str, Any]:
    outcomes = [record["outcomes"][str(horizon)] for record in records]
    complete = [outcome for outcome in outcomes if outcome["status"] == "complete"]
    returns = [outcome["return"] for outcome in complete]
    return {
        "total_blocks": len(records),
        "complete_samples": len(complete),
        "insufficient_future_data": sum(
            outcome["status"] == "insufficient_future_data" for outcome in outcomes
        ),
        "side_unavailable": sum(outcome["status"] == "side_unavailable" for outcome in outcomes),
        "completion_rate": len(complete) / len(records) if records else 0.0,
        "mean_return": _mean(returns),
        "median_return": _median(returns),
        "mean_MFE": _mean([outcome["MFE"] for outcome in complete]),
        "mean_MAE": _mean([outcome["MAE"] for outcome in complete]),
        "favorable_close_rate": (
            sum(value > 0 for value in returns) / len(returns) if returns else None
        ),
    }


def _wilson_interval(successes: int, total: int) -> tuple[float | None, float | None]:
    if total <= 0:
        return None, None
    z = 1.96
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _evidence_level(successes: int, total: int) -> str:
    lower, upper = _wilson_interval(successes, total)
    if lower is None or upper is None:
        return "LOW"
    if lower > 0.5:
        return "HIGH"
    if upper < 0.5:
        return "LOW"
    return "MEDIUM"


def _sample_size_level(total: int) -> str:
    if total >= 100:
        return "HIGH"
    if total >= 30:
        return "MEDIUM"
    return "LOW"


def _completion_level(rate: float) -> str:
    if rate >= 0.90:
        return "HIGH"
    if rate >= 0.70:
        return "MEDIUM"
    return "LOW"


def _consistency_level(metrics: dict[str, dict[str, Any]]) -> str:
    directions = []
    for horizon in HORIZONS:
        rate = metrics[str(horizon)]["favorable_close_rate"]
        if rate is not None:
            directions.append(rate > 0.5)
    if len(directions) < 3:
        return "LOW"
    majority = max(sum(directions), len(directions) - sum(directions))
    if majority == len(directions) and len(directions) == len(HORIZONS):
        return "HIGH"
    if majority >= 3:
        return "MEDIUM"
    return "LOW"


def _overall_confidence(sample: str, completion: str, consistency: str) -> str:
    levels = {sample, completion, consistency}
    if "LOW" in levels:
        return "LOW"
    if levels == {"HIGH"}:
        return "HIGH"
    return "MEDIUM"


def classify_state(cost_level: str, benefit_level: str, confidence: str) -> str:
    if confidence in {"HIGH", "MEDIUM"} and cost_level == "HIGH" and benefit_level == "LOW":
        return "EXPERIMENT"
    if confidence in {"HIGH", "MEDIUM"} and benefit_level == "HIGH" and cost_level == "LOW":
        return "KEEP"
    return "INVESTIGATE"


def _case(record: dict[str, Any] | None) -> dict[str, Any]:
    if record is None:
        return {
            "session_id": None,
            "timestamp": None,
            "side": None,
            "terminal_reason": None,
            "terminal_subreason": None,
            "return": None,
            "MFE": None,
            "MAE": None,
        }
    outcome = record["outcomes"][str(PRIMARY_HORIZON)]
    return {
        "session_id": record["session_id"],
        "timestamp": record["timestamp"],
        "side": record["side"],
        "terminal_reason": record["terminal_reason"],
        "terminal_subreason": record["terminal_subreason"],
        "return": outcome["return"],
        "MFE": outcome["MFE"],
        "MAE": outcome["MAE"],
    }


def _representative_cases(records: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [
        record
        for record in records
        if record["outcomes"][str(PRIMARY_HORIZON)]["status"] == "complete"
    ]
    ordered = sorted(
        complete,
        key=lambda record: (
            record["outcomes"][str(PRIMARY_HORIZON)]["return"],
            record["session_id"],
            str(record["timestamp"]),
        ),
    )
    if not ordered:
        return {
            "best_block": _case(None),
            "worst_block": _case(None),
            "representative_case": _case(None),
        }
    returns = [record["outcomes"][str(PRIMARY_HORIZON)]["return"] for record in ordered]
    median_return = statistics.median(returns)
    representative = min(
        ordered,
        key=lambda record: (
            abs(record["outcomes"][str(PRIMARY_HORIZON)]["return"] - median_return),
            record["session_id"],
            str(record["timestamp"]),
        ),
    )
    return {
        "best_block": _case(ordered[-1]),
        "worst_block": _case(ordered[0]),
        "representative_case": _case(representative),
    }


def _coverage_levels(counts: dict[str, int]) -> dict[str, str]:
    if not counts:
        return {}
    ordered = sorted(counts.values())
    low_cut = ordered[(len(ordered) - 1) // 3]
    high_cut = ordered[(2 * (len(ordered) - 1)) // 3]
    result = {}
    for name, count in counts.items():
        if count >= high_cut:
            result[name] = "HIGH"
        elif count >= low_cut:
            result[name] = "MEDIUM"
        else:
            result[name] = "LOW"
    return result


def build_scorecards(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filter_names = discover_filter_names(records)
    annotate_filter_activity(records, filter_names)
    total = len(records)
    blocked_records = [record for record in records if record.get("first_block")]
    valid_entry_failed = [
        record for record in records if record.get("terminal_reason") == "valid_entry_failed"
    ]
    grouped = {
        name: [record for record in blocked_records if name in record["active_filters"]]
        for name in filter_names
    }
    coverage_levels = _coverage_levels({name: len(rows) for name, rows in grouped.items()})
    cards = []
    for name in filter_names:
        rows = grouped[name]
        first_count = sum(record.get("first_block") == name for record in rows)
        metrics = {str(horizon): _horizon_metrics(rows, horizon) for horizon in HORIZONS}
        primary_complete = [
            record
            for record in rows
            if record["outcomes"][str(PRIMARY_HORIZON)]["status"] == "complete"
        ]
        favorable = sum(
            record["outcomes"][str(PRIMARY_HORIZON)]["return"] > 0
            for record in primary_complete
        )
        unfavorable = len(primary_complete) - favorable
        efnr_interval = _wilson_interval(favorable, len(primary_complete))
        epr_interval = _wilson_interval(unfavorable, len(primary_complete))
        sample_level = _sample_size_level(len(primary_complete))
        completion_level = _completion_level(metrics[str(PRIMARY_HORIZON)]["completion_rate"])
        consistency_level = _consistency_level(metrics)
        confidence = _overall_confidence(sample_level, completion_level, consistency_level)
        cost_level = _evidence_level(favorable, len(primary_complete))
        benefit_level = _evidence_level(unfavorable, len(primary_complete))
        state = classify_state(cost_level, benefit_level, confidence)
        card = {
            "filter": name,
            "coverage": {
                "total_blocks": len(rows),
                "first_blocks": first_count,
                "later_blocks": len(rows) - first_count,
                "percentage_of_structured_pipeline": _percentage(len(rows), total),
                "within_valid_entry_failed_count": sum(
                    name in record["active_filters"] for record in valid_entry_failed
                ),
                "percentage_within_valid_entry_failed": _percentage(
                    sum(name in record["active_filters"] for record in valid_entry_failed),
                    len(valid_entry_failed),
                ),
            },
            "outcomes": metrics,
            "quality": {
                "primary_horizon": PRIMARY_HORIZON,
                "definition": (
                    "EFNR is favorable blocked closes divided by directionally evaluable blocked "
                    "setups; EPR is non-favorable blocked closes divided by the same population."
                ),
                "evaluable_samples": len(primary_complete),
                "estimated_false_negative_rate": (
                    favorable / len(primary_complete) if primary_complete else None
                ),
                "estimated_false_negative_rate_wilson_95": list(efnr_interval),
                "estimated_protection_rate": (
                    unfavorable / len(primary_complete) if primary_complete else None
                ),
                "estimated_protection_rate_wilson_95": list(epr_interval),
            },
            "economics": {
                "primary_horizon": PRIMARY_HORIZON,
                "definition": (
                    "Filter Cost is the count of evaluable blocked setups with signed return > 0; "
                    "Filter Benefit is the count with signed return <= 0."
                ),
                "filter_cost": favorable,
                "filter_benefit": unfavorable,
            },
            "confidence": {
                "overall": confidence,
                "sample_size": sample_level,
                "horizon_completion": completion_level,
                "cross_horizon_consistency": consistency_level,
                "criteria": {
                    "sample_size": "HIGH n>=100; MEDIUM n>=30; LOW n<30 (binomial precision bands)",
                    "horizon_completion": "HIGH >=90%; MEDIUM >=70%; LOW <70% at +20",
                    "cross_horizon_consistency": "HIGH 4/4 same majority side; MEDIUM >=3; LOW otherwise",
                    "overall": "LOW if any component LOW; HIGH if all HIGH; otherwise MEDIUM",
                },
            },
            "representative_cases": _representative_cases(rows),
            "state": state,
            "decision_trace": {
                "Coverage": coverage_levels[name],
                "Coverage basis": (
                    "HIGH/MEDIUM/LOW is assigned by the upper/middle/lower data-relative "
                    "tercile of observed filter block counts."
                ),
                "Sample size": sample_level,
                "Estimated Cost": cost_level,
                "Estimated Benefit": benefit_level,
                "Confidence": confidence,
                "State": state,
                "rule": (
                    "EXPERIMENT when Cost HIGH, Benefit LOW, Confidence not LOW; KEEP when "
                    "Benefit HIGH, Cost LOW, Confidence not LOW; otherwise INVESTIGATE. "
                    "Cost/Benefit evidence is HIGH or LOW only when its Wilson 95% interval "
                    "lies wholly above or below 50%."
                ),
            },
        }
        cards.append(card)
    return sorted(cards, key=lambda card: card["filter"])


def _rank(cards: list[dict[str, Any]], key, value_name: str, reverse: bool = True) -> list[dict[str, Any]]:
    ordered = sorted(cards, key=lambda card: ((-key(card)) if reverse else key(card), card["filter"]))
    return [
        {"rank": rank, "filter": card["filter"], value_name: key(card)}
        for rank, card in enumerate(ordered, start=1)
    ]


def build_rankings(cards: list[dict[str, Any]]) -> dict[str, Any]:
    def uncertainty(card: dict[str, Any]) -> float:
        quality = card["quality"]
        interval = quality["estimated_false_negative_rate_wilson_95"]
        width = 1.0 if interval[0] is None else interval[1] - interval[0]
        completion = card["outcomes"][str(PRIMARY_HORIZON)]["completion_rate"]
        return width + (1.0 - completion)

    return {
        "highest_impact": _rank(
            cards, lambda card: card["coverage"]["total_blocks"], "total_blocks"
        ),
        "highest_cost": _rank(
            cards, lambda card: card["economics"]["filter_cost"], "filter_cost"
        ),
        "highest_benefit": _rank(
            cards, lambda card: card["economics"]["filter_benefit"], "filter_benefit"
        ),
        "highest_uncertainty": _rank(cards, uncertainty, "uncertainty_score"),
    }


def build_report(session_dirs: Iterable[Path]) -> dict[str, Any]:
    discovered = list(session_dirs)
    sessions = []
    invalid_sessions = []
    all_records = []
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
        all_records.extend(session["records"])
        sessions.append(
            {
                "session_id": session["session_id"],
                "session_path": session["session_path"],
                "record_count": session["record_count"],
                "structured_count": session["structured_count"],
                "summary_present": session["summary_present"],
            }
        )
    structured = [record for record in all_records if record["structured"]]
    blocked = [record for record in structured if record.get("first_block")]
    cards = build_scorecards(structured)
    states = Counter(card["state"] for card in cards)
    experiment_cards = sorted(
        (card for card in cards if card["state"] == "EXPERIMENT"),
        key=lambda card: (
            -(
                card["quality"]["estimated_false_negative_rate"]
                - card["quality"]["estimated_protection_rate"]
            ),
            -card["quality"]["evaluable_samples"],
            card["filter"],
        ),
    )
    experiment_candidates = [card["filter"] for card in experiment_cards]
    return {
        "report_version": 1,
        "analysis": "offline_decision_contract_filter_scorecard",
        "methodology": {
            "join": "ordinal_only",
            "horizons": list(HORIZONS),
            "primary_horizon": PRIMARY_HORIZON,
            "return_unit": "fraction_of_decision_price",
            "filter_discovery": (
                "Union of observed first blockers and non-pass values in dynamically discovered "
                "*_reason/terminal_subreason fields. Pass values are learned from accepted rows. "
                "Later blocks also use generic missing_*, *_missing, *_true, and *_false predicates "
                "against snapshot microstructure scalars. No filter-name allowlist is used."
            ),
            "side_evidence_order": (
                "decision detail, snapshot OB direction, displacement, momentum; unavailable otherwise"
            ),
            "confidence": (
                "Sample-size precision, +20 completion, and cross-horizon majority consistency; "
                "all thresholds are emitted in each filter decision trace."
            ),
            "uncertainty_ranking": (
                "Wilson 95% EFNR interval width plus the fraction not directionally complete at +20."
            ),
        },
        "sessions_discovered": len(discovered),
        "sessions_analyzed": len(sessions),
        "sessions_invalid": len(invalid_sessions),
        "sessions": sessions,
        "invalid_sessions": invalid_sessions,
        "coverage": {
            "pipeline_decisions_total": len(all_records),
            "structured_decisions": len(structured),
            "blocked_structured_decisions": len(blocked),
            "legacy_or_unstructured_excluded": len(all_records) - len(structured),
            "structured_coverage_percentage": _percentage(len(structured), len(all_records)),
        },
        "filters_discovered": len(cards),
        "scorecards": cards,
        "rankings": build_rankings(cards),
        "state_counts": dict(sorted(states.items())),
        "dcr_002_answer": {
            "question": (
                "If only one decision-contract filter could be modified, does any filter's "
                "benefit/risk relationship justify a controlled experiment?"
            ),
            "answer": experiment_candidates[0] if experiment_candidates else "No filter.",
            "experiment_candidates": experiment_candidates,
            "basis": "Only filters classified EXPERIMENT by the emitted reproducible rule qualify.",
            "selection_rule": (
                "If several qualify, select the largest EFNR-minus-EPR margin, then the largest "
                "evaluable sample, then filter name for a deterministic tie-break."
            ),
        },
        "safety": {
            "offline_only": True,
            "runtime_modified": False,
            "strategy_modified": False,
            "decision_contract_modified": False,
            "signals_reconstructed": False,
            "trading_simulated": False,
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
        "# BIUMOLO Decision Contract Filter Scorecard",
        "",
        f"- Sessions analyzed: {report['sessions_analyzed']} / {report['sessions_discovered']}",
        f"- Invalid sessions: {report['sessions_invalid']}",
        f"- Structured decisions: {coverage['structured_decisions']}",
        f"- Structured blocked decisions: {coverage['blocked_structured_decisions']}",
        f"- Filters discovered: {report['filters_discovered']}",
        "",
        "## DCR-002 answer",
        "",
        f"**{report['dcr_002_answer']['answer']}**",
        "",
        report["dcr_002_answer"]["basis"],
        "",
        "## Methodology",
        "",
        f"- Filter discovery: {report['methodology']['filter_discovery']}",
        f"- Side evidence: {report['methodology']['side_evidence_order']}",
        "- EFNR: favorable blocked closes / directionally evaluable blocked setups at +20.",
        "- EPR: non-favorable blocked closes / the same population at +20.",
        "- Filter Cost: count of evaluable blocked setups with signed return > 0 at +20.",
        "- Filter Benefit: count with signed return <= 0 at +20.",
        "",
        "## Rankings",
        "",
    ]
    for title, key, value_key in (
        ("Highest impact", "highest_impact", "total_blocks"),
        ("Highest cost", "highest_cost", "filter_cost"),
        ("Highest benefit", "highest_benefit", "filter_benefit"),
        ("Highest uncertainty", "highest_uncertainty", "uncertainty_score"),
    ):
        lines.extend([f"### {title}", "", "| Rank | Filter | Value |", "| ---: | --- | ---: |"])
        for item in report["rankings"][key]:
            lines.append(f"| {item['rank']} | {item['filter']} | {_fmt(item[value_key])} |")
        if not report["rankings"][key]:
            lines.append("| - | none | 0 |")
        lines.append("")

    lines.extend(["## Filter scorecards", ""])
    for card in report["scorecards"]:
        coverage = card["coverage"]
        quality = card["quality"]
        economics = card["economics"]
        trace = card["decision_trace"]
        lines.extend(
            [
                f"### {card['filter']}",
                "",
                f"- State: **{card['state']}**",
                f"- Total / first / later blocks: {coverage['total_blocks']} / "
                f"{coverage['first_blocks']} / {coverage['later_blocks']}",
                f"- Pipeline coverage: {coverage['percentage_of_structured_pipeline']:.2f}%",
                f"- Within valid_entry_failed: {coverage['percentage_within_valid_entry_failed']:.2f}%",
                f"- EFNR: {_fmt(quality['estimated_false_negative_rate'])}",
                f"- EPR: {_fmt(quality['estimated_protection_rate'])}",
                f"- Filter Cost / Benefit: {economics['filter_cost']} / {economics['filter_benefit']}",
                "",
                "#### Outcome metrics",
                "",
                "| Horizon | Complete | Mean return | Median return | Mean MFE | Mean MAE | Favorable close rate |",
                "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for horizon in HORIZONS:
            metric = card["outcomes"][str(horizon)]
            lines.append(
                f"| {horizon} | {metric['complete_samples']} | {_fmt(metric['mean_return'])} | "
                f"{_fmt(metric['median_return'])} | {_fmt(metric['mean_MFE'])} | "
                f"{_fmt(metric['mean_MAE'])} | {_fmt(metric['favorable_close_rate'])} |"
            )
        lines.extend(["", "#### Decision trace", ""])
        for key in ("Coverage", "Sample size", "Estimated Cost", "Estimated Benefit", "Confidence", "State"):
            lines.append(f"- {key}: **{trace[key]}**")
        lines.extend(["", "#### Representative cases", ""])
        for label, key in (
            ("Best block", "best_block"),
            ("Worst block", "worst_block"),
            ("Representative case", "representative_case"),
        ):
            case = card["representative_cases"][key]
            lines.append(
                f"- {label}: session={_fmt(case['session_id'])}, timestamp={_fmt(case['timestamp'])}, "
                f"side={_fmt(case['side'])}, reason={_fmt(case['terminal_reason'])}, "
                f"subreason={_fmt(case['terminal_subreason'])}, return={_fmt(case['return'])}, "
                f"MFE={_fmt(case['MFE'])}, MAE={_fmt(case['MAE'])}"
            )
        lines.append("")

    lines.extend(["## Invalid sessions", ""])
    if report["invalid_sessions"]:
        lines.extend(
            f"- `{item['session_id']}`: {item['reason']}" for item in report["invalid_sessions"]
        )
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
        description="Build the BIUMOLO decision-contract filter scorecard offline."
    )
    parser.add_argument("--sessions-root", default="logs/sessions")
    parser.add_argument("--output-json", default="analysis_reports/filter_scorecard.json")
    parser.add_argument("--output-md", default="analysis_reports/filter_scorecard.md")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(discover_sessions(Path(args.sessions_root)))
    json_path, md_path = write_reports(report, Path(args.output_json), Path(args.output_md))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Sessions analyzed: {report['sessions_analyzed']} / {report['sessions_discovered']}")
    print(f"Sessions invalid: {report['sessions_invalid']}")
    print(f"Structured decisions: {report['coverage']['structured_decisions']}")
    print(f"Filters discovered: {report['filters_discovered']}")
    print(f"DCR-002 answer: {report['dcr_002_answer']['answer']}")
    for item in report["invalid_sessions"]:
        print(f"Invalid session {item['session_id']}: {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
