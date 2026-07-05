import atexit
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from core.audit_session_logger_patch import (
    _read_jsonl_flexible,
    _read_text_flexible,
    enrich_summary_with_v2,
)

def _read_log_bom_safe(path):
    return _read_text_flexible(Path(path))

_REQUIRED_FILES = (
    "server_console.log",
    "feed_events.jsonl",
    "pipeline_decisions.jsonl",
    "signal_candidates.jsonl",
    "signals_enriched.jsonl",
    "dispatch_events.jsonl",
    "telegram_events.jsonl",
    "missed_trade_candidates.jsonl",
    "signal_engine_full_path_snapshots.jsonl",
    "session_summary.md",
    "session_summary.json",
)

_SESSION_DIR: Optional[Path] = None
_SESSION_ID: Optional[str] = None
_SESSION_META: dict[str, Any] = {}
_SUMMARY_REGISTERED = False


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _logs_root() -> Path:
    return _project_root() / "logs" / "sessions"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _ensure_required_files(session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    for name in _REQUIRED_FILES:
        path = session_dir / name
        if not path.exists():
            if path.suffix in {".jsonl", ".log", ".md"}:
                path.write_text("", encoding="utf-8")
            elif path.suffix == ".json":
                path.write_text("{}", encoding="utf-8")
            else:
                path.touch()


def _safe_session_name(now: datetime) -> str:
    return now.astimezone().strftime("%Y%m%d_%H%M%S")


def _redact_string(value: str) -> str:
    if not value:
        return value
    lowered = value.lower()
    if "telegram" in lowered and "token" in lowered:
        return "***REDACTED***"
    if len(value) > 24 and ":" in value:
        return value[:4] + "***REDACTED***" + value[-4:]
    return value


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if "token" in key_lower:
                redacted[key] = "***REDACTED***"
            elif key_lower in {"chat_id", "telegram_chat_id"}:
                text = str(item)
                redacted[key] = text[:2] + "***REDACTED***" + text[-2:] if len(text) > 4 else "***REDACTED***"
            else:
                redacted[key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return _redact_string(value)
    return value


def start_session(metadata: Optional[dict[str, Any]] = None) -> str:
    global _SESSION_DIR, _SESSION_ID, _SESSION_META, _SUMMARY_REGISTERED

    if _SESSION_DIR is not None:
        if metadata:
            _SESSION_META.update(redact_sensitive(metadata))
            _write_session_metadata()
        return str(_SESSION_DIR)

    env_dir = os.getenv("BIUMOLO_SESSION_DIR")
    if env_dir:
        session_dir = Path(env_dir)
        session_id = session_dir.name
    else:
        now = _utc_now()
        session_id = _safe_session_name(now)
        session_dir = _logs_root() / session_id

    _SESSION_DIR = session_dir
    _SESSION_ID = session_id
    _SESSION_META = redact_sensitive(metadata or {})
    _SESSION_META.setdefault("session_id", session_id)
    _SESSION_META.setdefault("started_at_utc", _iso(_utc_now()))
    _SESSION_META.setdefault("started_at_local", datetime.now().astimezone().isoformat())

    _ensure_required_files(session_dir)
    _write_session_metadata()

    if not _SUMMARY_REGISTERED:
        atexit.register(write_session_summary)
        _SUMMARY_REGISTERED = True

    return str(session_dir)


def get_session_dir() -> str:
    if _SESSION_DIR is None:
        start_session()
    return str(_SESSION_DIR)


def get_session_id() -> str:
    if _SESSION_ID is None:
        start_session()
    return str(_SESSION_ID)


def _write_session_metadata() -> None:
    if _SESSION_DIR is None:
        return
    metadata_path = _SESSION_DIR / "session_metadata.json"
    metadata_path.write_text(
        json.dumps(redact_sensitive(_SESSION_META), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def append_jsonl(filename: str, record: dict[str, Any]) -> None:
    session_dir = Path(get_session_dir())
    path = session_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_record = redact_sensitive(record)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(clean_record, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl_flexible(path)


def _count_reason(records: Iterable[dict[str, Any]], key: str) -> Counter:
    counter: Counter = Counter()
    for record in records:
        reason = record.get(key)
        if reason:
            counter[str(reason)] += 1
    return counter


def _parse_console_stats(console_text: str) -> dict[str, int]:
    return {
        "websocket_reconnects": console_text.count("RECONNECTING"),
        "duplicate_connections": console_text.count("conexion previa detectada"),
    }


def _build_summary(session_dir: Path) -> dict[str, Any]:
    feed_records = _read_jsonl(session_dir / "feed_events.jsonl")
    decision_records = _read_jsonl(session_dir / "pipeline_decisions.jsonl")
    signal_candidates = _read_jsonl(session_dir / "signal_candidates.jsonl")
    enriched_signals = _read_jsonl(session_dir / "signals_enriched.jsonl")
    dispatch_records = _read_jsonl(session_dir / "dispatch_events.jsonl")
    telegram_records = _read_jsonl(session_dir / "telegram_events.jsonl")
    missed_records = _read_jsonl(session_dir / "missed_trade_candidates.jsonl")

    console_path = session_dir / "server_console.log"
    console_text = _read_text_flexible(console_path)
    console_stats = _parse_console_stats(console_text)

    no_trade_reasons = Counter()
    for record in decision_records:
        if record.get("final_decision") == "NO_TRADE":
            no_trade_reasons[str(record.get("final_reason") or "unknown")] += 1

    signals_table = []
    for record in enriched_signals:
        signals_table.append(
            {
                "time_local": record.get("created_at_local"),
                "side": record.get("side"),
                "entry": record.get("entry"),
                "stop": record.get("stop"),
                "tp1": record.get("tp1"),
                "tp2": record.get("tp2"),
                "tp3": record.get("tp3"),
                "dispatch_status": record.get("dispatch_status"),
            }
        )

    summary = {
        "session_id": _SESSION_META.get("session_id", session_dir.name),
        "started_at_utc": _SESSION_META.get("started_at_utc"),
        "started_at_local": _SESSION_META.get("started_at_local"),
        "ended_at_utc": _iso(_utc_now()),
        "ended_at_local": datetime.now().astimezone().isoformat(),
        "total_velas_recibidas": len(feed_records),
        "total_feed_accepted": sum(1 for r in feed_records if r.get("feed_accepted") is True),
        "total_feed_rejected": sum(1 for r in feed_records if r.get("feed_accepted") is False),
        "total_pipeline_executed": sum(1 for r in feed_records if r.get("pipeline_executed") is True),
        "total_signal_candidates": len(signal_candidates),
        "total_senales_generadas": len(enriched_signals),
        "total_senales_despachadas": sum(1 for r in dispatch_records if r.get("allowed") is True),
        "total_senales_bloqueadas": sum(1 for r in dispatch_records if r.get("allowed") is False),
        "total_telegram_sent": sum(1 for r in telegram_records if r.get("sent") is True),
        "total_telegram_failed": sum(1 for r in telegram_records if r.get("sent") is False),
        "signals_table": signals_table,
        "top_no_trade_reasons": no_trade_reasons.most_common(15),
        "near_miss_candidates": [r for r in missed_records if r.get("classification") == "near_miss_candidate"],
        "possible_false_negative_pending_review": [
            r for r in missed_records if r.get("classification") == "possible_false_negative_pending_review"
        ],
        "platform_stable": console_stats["duplicate_connections"] == 0,
        "websocket_reconnects": console_stats["websocket_reconnects"],
        "duplicate_connections": console_stats["duplicate_connections"],
        "notes": [
            "No usar cuenta real.",
            "Resumen regenerado desde archivos de sesión.",
        ],
    }
    return enrich_summary_with_v2(summary, session_dir)


def _format_summary_md(summary: dict[str, Any]) -> str:
    def line(label: str, value: Any) -> str:
        return f"- **{label}:** {value}"

    signals_lines = []
    for row in summary.get("signals_table", []):
        signals_lines.append(
            f"| {row.get('time_local')} | {row.get('side')} | {row.get('entry')} | {row.get('stop')} | "
            f"{row.get('tp1')} | {row.get('tp2')} | {row.get('tp3')} | {row.get('dispatch_status')} |"
        )
    if not signals_lines:
        signals_lines.append("| - | - | - | - | - | - | - | - |")

    reason_lines = [f"- {reason}: {count}" for reason, count in summary.get("top_no_trade_reasons", [])] or ["- none"]
    near_miss_lines = [
        f"- {item.get('timestamp')} {item.get('classification')} {item.get('primary_block')}"
        for item in summary.get("near_miss_candidates", [])
    ] or ["- none"]
    possible_false_negative_lines = [
        f"- {item.get('timestamp')} {item.get('classification')} {item.get('primary_block')}"
        for item in summary.get("possible_false_negative_pending_review", [])
    ] or ["- none"]

    return "\n".join(
        [
            "# BIUMOLO Session Summary",
            "",
            line("Session ID", summary.get("session_id")),
            line("Started UTC", summary.get("started_at_utc")),
            line("Started Local", summary.get("started_at_local")),
            line("Ended UTC", summary.get("ended_at_utc")),
            line("Ended Local", summary.get("ended_at_local")),
            "",
            "## Totals",
            line("Velas recibidas", summary.get("total_velas_recibidas")),
            line("Feed accepted", summary.get("total_feed_accepted")),
            line("Feed rejected", summary.get("total_feed_rejected")),
            line("Pipeline executed", summary.get("total_pipeline_executed")),
            line("Señales generadas", summary.get("total_senales_generadas")),
            line("Señales despachadas", summary.get("total_senales_despachadas")),
            line("Señales bloqueadas", summary.get("total_senales_bloqueadas")),
            line("Telegram sent", summary.get("total_telegram_sent")),
            line("Telegram failed", summary.get("total_telegram_failed")),
            "",
            "## Final signals",
            "| Hora local | Side | Entry | Stop | TP1 | TP2 | TP3 | Dispatch |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
            *signals_lines,
            "",
            "## Top NO_TRADE reasons",
            *reason_lines,
            "",
            "## Near miss candidates",
            *near_miss_lines,
            "",
            "## Possible false negatives pending review",
            *possible_false_negative_lines,
            "",
            "## Platform state",
            line("platform_stable", summary.get("platform_stable")),
            line("websocket_reconnects", summary.get("websocket_reconnects")),
            line("duplicate_connections", summary.get("duplicate_connections")),
            "",
        ]
    )


def write_session_summary(session_dir: Optional[str] = None) -> dict[str, Any]:
    path = Path(session_dir or get_session_dir())
    path.mkdir(parents=True, exist_ok=True)
    summary = _build_summary(path)
    (path / "session_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (path / "session_summary.md").write_text(
        _format_summary_md(summary),
        encoding="utf-8",
    )
    return summary
