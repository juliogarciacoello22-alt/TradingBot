from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

_GENERATED_REASONS = {"scalper_generated", "swing_generated"}
_REASON_FIELDS = (
    "terminal_stage",
    "terminal_reason",
    "terminal_subreason",
    "build_signal_reason",
    "valid_entry_reason",
    "ob_reason",
    "timing_reason",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for raw_line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def sorted_counts(values: Iterable[Any]) -> dict[str, int]:
    counter = Counter(str(value) for value in values if value not in (None, ""))
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def classify_telemetry(records: list[dict[str, Any]]) -> str:
    if not records:
        return 'EMPTY'
    structured_count = sum(
        1
        for record in records
        if any(record.get(field) not in (None, '') for field in _REASON_FIELDS)
    )
    if structured_count == 0:
        return 'LEGACY'
    if structured_count == len(records):
        return 'FULL'
    return 'PARTIAL'


def structured_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if any(record.get(field) not in (None, '') for field in _REASON_FIELDS)
    ]


def analyze_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    build_generated = sum(
        1 for record in records if record.get("build_signal_reason") in _GENERATED_REASONS
    )
    final_signals = sum(
        1
        for record in records
        if record.get("terminal_stage") == "final_signal"
        and record.get("terminal_reason") == "ok"
    )
    execution_rejected = sum(
        1 for record in records if record.get("terminal_reason") == "execution_rejected"
    )

    counts = {
        field: sorted_counts(record.get(field) for record in records)
        for field in _REASON_FIELDS
    }

    dominant_filters = []
    for reason, count in counts["terminal_subreason"].items():
        share = percentage(count, total)
        if count >= 10 and share >= 10.0:
            dominant_filters.append(
                {"reason": reason, "count": count, "share_of_pipeline_pct": share}
            )

    warnings: list[str] = []
    if total == 0:
        warnings.append("no_pipeline_decisions")
    elif total < 100:
        warnings.append("small_pipeline_sample_under_100")
    if 0 < build_generated < 10:
        warnings.append("small_generated_signal_sample_under_10")
    if build_generated == 0:
        warnings.append("no_generated_build_signals")

    structured = structured_records(records)

    return {
        "pipeline_decisions": total,
        "structured_decisions": len(structured),
        "telemetry_class": classify_telemetry(records),
        "funnel": {
            "build_signal_generated": build_generated,
            "final_signals": final_signals,
            "execution_rejected": execution_rejected,
            "pipeline_to_build_signal_pct": percentage(build_generated, total),
            "build_signal_to_final_pct": percentage(final_signals, build_generated),
            "build_signal_to_execution_rejected_pct": percentage(
                execution_rejected, build_generated
            ),
        },
        "reason_counts": counts,
        "dominant_filters": dominant_filters,
        "warnings": warnings,
    }


def discover_sessions(sessions_root: Path) -> list[Path]:
    if not sessions_root.exists():
        return []
    return sorted(
        (
            path
            for path in sessions_root.iterdir()
            if path.is_dir() and (path / "pipeline_decisions.jsonl").exists()
        ),
        key=lambda path: path.name,
    )


def build_report(session_dirs: list[Path]) -> dict[str, Any]:
    sessions = []
    all_records: list[dict[str, Any]] = []
    all_structured_records: list[dict[str, Any]] = []

    for session_dir in session_dirs:
        records = read_jsonl(session_dir / "pipeline_decisions.jsonl")
        analysis = analyze_records(records)
        sessions.append({"session_id": session_dir.name, **analysis})
        all_records.extend(records)
        all_structured_records.extend(structured_records(records))

    aggregate = analyze_records(all_records)
    structured_aggregate = analyze_records(all_structured_records)
    coverage_pct = percentage(len(all_structured_records), len(all_records))
    class_counts = sorted_counts(session["telemetry_class"] for session in sessions)

    report_warnings = list(aggregate["warnings"])
    if not session_dirs:
        report_warnings.append("no_sessions_discovered")
    if all_records and coverage_pct < 80.0:
        report_warnings.append("structured_telemetry_coverage_below_80_percent")

    return {
        "report_version": 2,
        "sessions_analyzed": len(session_dirs),
        "session_ids": [path.name for path in session_dirs],
        "telemetry_coverage": {
            "pipeline_decisions_total": len(all_records),
            "structured_decisions": len(all_structured_records),
            "coverage_percent": coverage_pct,
            "session_class_counts": class_counts,
        },
        "aggregate": aggregate,
        "structured_aggregate": structured_aggregate,
        "sessions": sessions,
        "warnings": report_warnings,
        "safety": {
            "offline_only": True,
            "runtime_modified": False,
            "trading_modified": False,
        },
    }


def format_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    structured_aggregate = report.get("structured_aggregate", aggregate)
    funnel = aggregate["funnel"]
    structured_funnel = structured_aggregate["funnel"]
    coverage = report.get("telemetry_coverage", {})
    lines = [
        "# BIUMOLO Offline Strategy Behavior Report",
        "",
        f"- **Sessions analyzed:** {report['sessions_analyzed']}",
        f"- **Pipeline decisions:** {aggregate['pipeline_decisions']}",
        f"- **Build signals generated:** {funnel['build_signal_generated']}",
        f"- **Final signals:** {funnel['final_signals']}",
        f"- **Execution rejected:** {funnel['execution_rejected']}",
        f"- **Structured decisions:** {coverage.get('structured_decisions', 0)}",
        f"- **Structured telemetry coverage:** {coverage.get('coverage_percent', 0.0)}%",
        "",
        "## Global/raw funnel",
        "",
        f"- Pipeline → build signal: {funnel['pipeline_to_build_signal_pct']}%",
        f"- Build signal → final signal: {funnel['build_signal_to_final_pct']}%",
        f"- Build signal → execution rejected: {funnel['build_signal_to_execution_rejected_pct']}%",
        "",
        "## Comparable structured funnel",
        "",
        f"- Structured pipeline decisions: {structured_aggregate['pipeline_decisions']}",
        f"- Pipeline → build signal: {structured_funnel['pipeline_to_build_signal_pct']}%",
        f"- Build signal → final signal: {structured_funnel['build_signal_to_final_pct']}%",
        f"- Build signal → execution rejected: {structured_funnel['build_signal_to_execution_rejected_pct']}%",
        "",
        "## Dominant terminal subreasons",
        "",
    ]

    dominant = structured_aggregate["dominant_filters"]
    if dominant:
        lines.extend(
            f"- {item['reason']}: {item['count']} ({item['share_of_pipeline_pct']}%)"
            for item in dominant
        )
    else:
        lines.append("- none")

    for field in ("terminal_reason", "terminal_subreason", "ob_reason", "timing_reason"):
        lines.extend(["", f"## {field}", ""])
        counts = structured_aggregate["reason_counts"][field]
        if counts:
            lines.extend(f"- {reason}: {count}" for reason, count in counts.items())
        else:
            lines.append("- none")

    lines.extend(["", "## Session comparison", ""])
    if report["sessions"]:
        lines.extend(
            [
                "| Session | Class | Pipeline | Structured | Build signals | Final | Execution rejected |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for session in report["sessions"]:
            session_funnel = session["funnel"]
            lines.append(
                f"| {session['session_id']} | {session.get('telemetry_class', 'LEGACY')} | "
                f"{session['pipeline_decisions']} | {session.get('structured_decisions', 0)} | "
                f"{session_funnel['build_signal_generated']} | "
                f"{session_funnel['final_signals']} | "
                f"{session_funnel['execution_rejected']} |"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Warnings", ""])
    warnings = report.get("warnings") or []
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "strategy_behavior_report.json"
    md_path = output_dir / "strategy_behavior_report.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8-sig",
    )
    md_path.write_text(format_markdown(report), encoding="utf-8-sig")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze BIUMOLO pipeline behavior from session JSONL files."
    )
    parser.add_argument("--sessions-root", default="logs/sessions")
    parser.add_argument("--output-dir", default="analysis_reports")
    parser.add_argument(
        "--session",
        action="append",
        default=[],
        help="Specific session directory name. Repeat to select multiple sessions.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sessions_root = Path(args.sessions_root)
    if args.session:
        session_dirs = [sessions_root / name for name in args.session]
    else:
        session_dirs = discover_sessions(sessions_root)

    report = build_report(session_dirs)
    json_path, md_path = write_report(report, Path(args.output_dir))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Sessions analyzed: {report['sessions_analyzed']}")
    print(f"Pipeline decisions: {report['aggregate']['pipeline_decisions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
