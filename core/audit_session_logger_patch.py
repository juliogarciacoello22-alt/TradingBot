import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


_BUILD_SIGNAL_RE = re.compile(r"BUILD_SIGNAL RESULT[^\n]*\breason=([^\s]+)")
_FINAL_REASON_RE = re.compile(r"\bfinal_reason=([^\s]+)")
_DISPATCH_RESULT_RE = re.compile(r"PIPELINE DISPATCH RESULT[^\n]*\ballowed=([^\s]+)[^\n]*\breason=([^\s]+)")
_SIGNAL_GENERATED_REASONS = {"scalper_generated", "swing_generated"}


def _read_text_flexible(path: Path) -> str:
    if not path.exists():
        return ""

    data = path.read_bytes()
    if not data:
        return ""

    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16le", errors="replace")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16be", errors="replace")

    sample = data[:2000]
    if sample and sample.count(b"\x00") / max(len(sample), 1) > 0.2:
        return data.decode("utf-16le", errors="replace")

    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _read_jsonl_flexible(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in _read_text_flexible(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def _as_count_pairs(counter: Counter) -> list[list[Any]]:
    return [[key, value] for key, value in counter.most_common(20)]


def _max_int(*values: Any) -> int:
    ints = []
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            ints.append(value)
    return max(ints or [0])


def _console_metrics(console_text: str) -> dict[str, Any]:
    build_signal_reasons = Counter(_BUILD_SIGNAL_RE.findall(console_text))
    dispatch_block_reasons = Counter()
    dispatch_allowed = 0
    dispatch_blocked = 0

    for allowed, reason in _DISPATCH_RESULT_RE.findall(console_text):
        if allowed == "True":
            dispatch_allowed += 1
        elif allowed == "False":
            dispatch_blocked += 1
            dispatch_block_reasons[reason] += 1

    generated = sum(build_signal_reasons.get(reason, 0) for reason in _SIGNAL_GENERATED_REASONS)

    return {
        "build_signal_results": sum(build_signal_reasons.values()),
        "build_signal_reasons": build_signal_reasons,
        "signal_engine_generated": generated,
        "pipeline_decisions": console_text.count("PIPELINE DECISION"),
        "microstructure_decisions": console_text.count("MICROSTRUCTURE DECISION"),
        "ob_engine_decisions": console_text.count("OB ENGINE DECISION"),
        "risk_engine_cancelled": console_text.count("SENAL CANCELADA POR RISKENGINE"),
        "timing_engine_cancelled": console_text.count("SENAL CANCELADA POR TIMINGENGINE"),
        "historical_only_logged": console_text.count("MODO HISTORICO"),
        "dispatch_allowed": dispatch_allowed,
        "dispatch_blocked": dispatch_blocked,
        "dispatch_block_reasons": dispatch_block_reasons,
        "final_reasons": Counter(_FINAL_REASON_RE.findall(console_text)),
    }


def _snapshot_metrics(snapshot_records: list[dict[str, Any]]) -> dict[str, Any]:
    terminal_reasons: Counter = Counter()
    generated = 0

    for record in snapshot_records:
        reason = (
            record.get("terminal_reason")
            or record.get("final_reason")
            or record.get("reason")
            or record.get("signal_reason")
        )
        if reason:
            terminal_reasons[str(reason)] += 1
        if reason in _SIGNAL_GENERATED_REASONS:
            generated += 1

    return {
        "full_path_snapshots": len(snapshot_records),
        "terminal_reasons": terminal_reasons,
        "signal_engine_generated": generated,
    }


def enrich_summary_with_v2(summary: dict[str, Any], session_dir: Path) -> dict[str, Any]:
    enriched = dict(summary)

    feed_records = _read_jsonl_flexible(session_dir / "feed_events.jsonl")
    decision_records = _read_jsonl_flexible(session_dir / "pipeline_decisions.jsonl")
    signal_candidates = _read_jsonl_flexible(session_dir / "signal_candidates.jsonl")
    enriched_signals = _read_jsonl_flexible(session_dir / "signals_enriched.jsonl")
    dispatch_records = _read_jsonl_flexible(session_dir / "dispatch_events.jsonl")
    telegram_records = _read_jsonl_flexible(session_dir / "telegram_events.jsonl")
    snapshot_records = _read_jsonl_flexible(session_dir / "signal_engine_full_path_snapshots.jsonl")

    console_text = _read_text_flexible(session_dir / "server_console.log")
    console = _console_metrics(console_text)
    snapshots = _snapshot_metrics(snapshot_records)

    decision_reason_counts = Counter(
        str(record.get("final_reason") or "unknown")
        for record in decision_records
        if record.get("final_decision") == "NO_TRADE"
    )
    dispatch_block_reasons = Counter(
        str(record.get("reason") or record.get("dispatch_status") or "unknown")
        for record in dispatch_records
        if record.get("allowed") is False
    )
    dispatch_block_reasons.update(console["dispatch_block_reasons"])

    observed_pipeline = _max_int(
        enriched.get("total_pipeline_executed"),
        sum(1 for record in feed_records if record.get("pipeline_executed") is True),
        len(decision_records),
        console["pipeline_decisions"],
        console["build_signal_results"],
        snapshots["full_path_snapshots"],
    )
    structured_build_signal_generated = sum(
        1
        for record in decision_records
        if record.get("build_signal_reason") in _SIGNAL_GENERATED_REASONS
    )
    observed_build_signal_results = _max_int(
        console["build_signal_results"],
        structured_build_signal_generated,
        enriched.get("total_build_signal_generated"),
    )
    observed_generated = _max_int(
        len(enriched_signals),
        len(signal_candidates),
        console["signal_engine_generated"],
        snapshots["signal_engine_generated"],
        enriched.get("total_senales_generadas"),
    )

    enriched["total_velas_recibidas"] = _max_int(enriched.get("total_velas_recibidas"), len(feed_records))
    enriched["total_feed_accepted"] = _max_int(
        enriched.get("total_feed_accepted"),
        sum(1 for record in feed_records if record.get("feed_accepted") is True),
    )
    enriched["total_feed_rejected"] = _max_int(
        enriched.get("total_feed_rejected"),
        sum(1 for record in feed_records if record.get("feed_accepted") is False),
    )
    enriched["total_pipeline_executed"] = observed_pipeline
    enriched["total_signal_candidates"] = _max_int(
        enriched.get("total_signal_candidates"),
        len(signal_candidates),
        console["signal_engine_generated"],
        snapshots["signal_engine_generated"],
    )
    enriched["total_senales_generadas"] = observed_generated
    enriched["total_senales_finales_enriquecidas"] = len(enriched_signals)
    enriched["total_senales_despachadas"] = _max_int(
        enriched.get("total_senales_despachadas"),
        sum(1 for record in dispatch_records if record.get("allowed") is True),
        console["dispatch_allowed"],
    )
    enriched["total_senales_bloqueadas"] = _max_int(
        enriched.get("total_senales_bloqueadas"),
        sum(1 for record in dispatch_records if record.get("allowed") is False),
        console["dispatch_blocked"],
    )
    enriched["total_telegram_sent"] = _max_int(
        enriched.get("total_telegram_sent"),
        sum(1 for record in telegram_records if record.get("sent") is True),
    )
    enriched["total_telegram_failed"] = _max_int(
        enriched.get("total_telegram_failed"),
        sum(1 for record in telegram_records if record.get("sent") is False),
    )

    combined_reasons = Counter(decision_reason_counts)
    combined_reasons.update(console["final_reasons"])
    combined_reasons.update(snapshots["terminal_reasons"])
    if combined_reasons:
        enriched["top_no_trade_reasons"] = combined_reasons.most_common(15)

    warnings = []
    if summary.get("total_pipeline_executed") == 0 and observed_pipeline > 0:
        warnings.append("base_summary_pipeline_zero_but_logs_show_activity")
    if summary.get("total_senales_generadas") == 0 and observed_generated > 0:
        warnings.append("base_summary_signals_zero_but_logs_show_generated_signals")
    if console["build_signal_results"] == 0 and structured_build_signal_generated > 0:
        warnings.append(
            "summary_v2_build_signal_zero_but_pipeline_decisions_show_generated"
        )
    if observed_generated > len(enriched_signals):
        warnings.append("signal_engine_generated_exceeds_final_enriched_signals")

    enriched["summary_v2"] = {
        "version": 2,
        "source_files": {
            "feed_events": len(feed_records),
            "pipeline_decisions": len(decision_records),
            "signal_candidates": len(signal_candidates),
            "signals_enriched": len(enriched_signals),
            "dispatch_events": len(dispatch_records),
            "telegram_events": len(telegram_records),
            "full_path_snapshots": snapshots["full_path_snapshots"],
            "server_console_bytes": len(console_text.encode("utf-8", errors="replace")),
        },
        "observed_activity": {
            "pipeline_executed": observed_pipeline,
            "build_signal_results": observed_build_signal_results,
            "microstructure_decisions": console["microstructure_decisions"],
            "ob_engine_decisions": console["ob_engine_decisions"],
            "full_path_snapshots": snapshots["full_path_snapshots"],
            "signal_engine_generated": observed_generated,
            "risk_engine_cancelled": console["risk_engine_cancelled"],
            "timing_engine_cancelled": console["timing_engine_cancelled"],
            "historical_only_logged": console["historical_only_logged"],
        },
        "build_signal_reasons": _as_count_pairs(console["build_signal_reasons"]),
        "dispatch_block_reasons": _as_count_pairs(dispatch_block_reasons),
        "snapshot_terminal_reasons": _as_count_pairs(snapshots["terminal_reasons"]),
        "consistency_warnings": warnings,
    }
    if warnings:
        notes = list(enriched.get("notes") or [])
        notes.extend(f"summary_v2_warning:{warning}" for warning in warnings)
        enriched["notes"] = notes

    return enriched
