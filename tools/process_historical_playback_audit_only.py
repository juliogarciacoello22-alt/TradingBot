"""Process imported historical/playback feed artifacts in audit-only mode.

This processor consumes a PR24 feed-only session created by
tools/import_historical_playback_readonly.py and writes minimal pipeline audit
evidence. It does not import server.py, instantiate live engines, load .env,
open WebSockets, use Telegram, call send_signal, or generate orders.

The generated evidence proves that imported feed rows were accepted and passed
through a no-dispatch audit pipeline stage. It does not claim SignalEngineV4
build_signal execution, SHADOW vs REAL conclusions, Sim101 execution, or Live
execution.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SESSION_FILES = (
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
    "session_metadata.json",
)


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
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row is not an object in {path}")
        rows.append(value)
    return rows


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = _read_text(path).strip()
    if not text:
        return {}
    value = json.loads(text)
    return value if isinstance(value, dict) else {}


def _ensure_session_files(session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    for name in SESSION_FILES:
        path = session_dir / name
        if path.exists():
            continue
        if path.suffix == ".json":
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.write_text("", encoding="utf-8")


def _require_imported_feed_session(session_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    metadata = _load_json(session_dir / "session_metadata.json")
    feed_events = read_jsonl(session_dir / "feed_events.jsonl")

    if not feed_events:
        raise ValueError("feed_events.jsonl is empty; run the PR24 importer first")
    if metadata.get("source_type") != "historical_playback":
        raise ValueError("session_metadata.json must have source_type=historical_playback")
    if metadata.get("no_dispatch") is not True or metadata.get("no_live") is not True:
        raise ValueError("imported session must preserve no_dispatch=true and no_live=true")
    if metadata.get("orders_sent", 0) != 0:
        raise ValueError("imported session must have orders_sent=0")

    return feed_events, metadata


def _feed_timestamp(feed: dict[str, Any]) -> Any:
    return feed.get("timestamp") or feed.get("time") or feed.get("datetime")


def _feed_price(feed: dict[str, Any]) -> Any:
    return feed.get("close") if "close" in feed else feed.get("price")


def _decision_row(session_id: str, sequence: int, feed: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": "pipeline_decision",
        "session_id": session_id,
        "sequence": sequence,
        "timestamp": _feed_timestamp(feed),
        "final_decision": "NO_TRADE",
        "final_reason": "audit_only_feed_replay_no_signal_engine",
        "detail": "feed row accepted by audit-only processor; SignalEngineV4 was not called",
        "audit_only": True,
        "pipeline_processing_mode": "AUDIT_ONLY_FEED_REPLAY",
        "source_type": "historical_playback",
        "feed_accepted": bool(feed.get("feed_accepted", True)),
        "signal_engine_called": False,
        "build_signal_called": False,
        "dispatch_attempted": False,
        "send_signal_called": False,
        "telegram_attempted": False,
        "websocket_opened": False,
        "orders_sent": 0,
        "no_dispatch": True,
        "no_live": True,
    }


def _snapshot_row(session_id: str, sequence: int, feed: dict[str, Any]) -> dict[str, Any]:
    timestamp = _feed_timestamp(feed)
    decision_id = f"{session_id}|audit_feed|{sequence}"
    return {
        "event": "signal_engine_v4_full_path_snapshot",
        "snapshot": {
            "decision_id": decision_id,
            "timestamp": timestamp,
            "audit_only": True,
            "pipeline_processing_mode": "AUDIT_ONLY_FEED_REPLAY",
            "source_type": "historical_playback",
            "feed_event": {
                "sequence": sequence,
                "timestamp": timestamp,
                "open": feed.get("open"),
                "high": feed.get("high"),
                "low": feed.get("low"),
                "close": feed.get("close"),
                "volume": feed.get("volume"),
                "feed_accepted": bool(feed.get("feed_accepted", True)),
            },
            "last_candle": {
                "timestamp": timestamp,
                "open": feed.get("open"),
                "high": feed.get("high"),
                "low": feed.get("low"),
                "close": feed.get("close"),
                "volume": feed.get("volume"),
            },
            "price": _feed_price(feed),
            "stage_outputs": {
                "feed_validation": {
                    "accepted": bool(feed.get("feed_accepted", True)),
                    "reason": "historical_playback_feed_row_accepted",
                },
                "signal_engine": {
                    "signal_engine_called": False,
                    "build_signal_called": False,
                    "signal_is_none": True,
                    "last_build_signal_reason": None,
                    "last_valid_entry_reason": None,
                    "last_valid_entry_shadow": {},
                },
                "dispatch": {
                    "dispatch_attempted": False,
                    "send_signal_called": False,
                    "no_dispatch": True,
                },
            },
            "missing_fields": [],
            "interpretation_guard": (
                "This snapshot is audit-only feed replay evidence. It is not a "
                "SignalEngineV4 build_signal result and not a trade authorization."
            ),
        },
    }


def _summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Historical Playback Audit-Only Processing",
            "",
            f"- session_id: `{summary['session_id']}`",
            "- pipeline_processing_mode: `AUDIT_ONLY_FEED_REPLAY`",
            f"- feed_events: `{summary['feed_events']}`",
            f"- pipeline_decisions: `{summary['pipeline_decisions']}`",
            f"- full_path_snapshots: `{summary['full_path_snapshots']}`",
            "- signal_engine_called: `false`",
            "- build_signal_called: `false`",
            "- no_dispatch: `true`",
            "- no_live: `true`",
            "- orders_sent: `0`",
            "",
            "This session contains audit-only feed replay evidence. It does not",
            "claim SHADOW vs REAL signal conclusions, Sim101 execution, Live",
            "execution, dispatch, Telegram delivery, or orders.",
            "",
        ]
    )


def process_historical_playback_audit_only(session_dir: Path) -> Path:
    session_dir = Path(session_dir)
    _ensure_session_files(session_dir)
    feed_events, metadata = _require_imported_feed_session(session_dir)

    session_id = str(metadata.get("session_id") or session_dir.name)
    decisions = [_decision_row(session_id, index, feed) for index, feed in enumerate(feed_events, start=1)]
    snapshots = [_snapshot_row(session_id, index, feed) for index, feed in enumerate(feed_events, start=1)]

    _write_jsonl(session_dir / "pipeline_decisions.jsonl", decisions)
    _write_jsonl(session_dir / "signal_engine_full_path_snapshots.jsonl", snapshots)
    _write_jsonl(session_dir / "dispatch_events.jsonl", [])
    _write_jsonl(session_dir / "telegram_events.jsonl", [])

    processed_at = datetime.now(timezone.utc).isoformat()
    summary = {
        **metadata,
        "session_id": session_id,
        "audit_pipeline_processed": True,
        "pipeline_processed": True,
        "pipeline_processing_mode": "AUDIT_ONLY_FEED_REPLAY",
        "processed_at_utc": processed_at,
        "feed_events": len(feed_events),
        "pipeline_decisions": len(decisions),
        "full_path_snapshots": len(snapshots),
        "signal_engine_called": False,
        "build_signal_called": False,
        "send_signal_called": False,
        "websocket_opened": False,
        "telegram_enabled": False,
        "orders_sent": 0,
        "no_dispatch": True,
        "no_live": True,
        "interpretation_guards": [
            "pipeline_decisions are audit-only feed replay rows",
            "signal_engine_full_path_snapshots are feed-validation snapshots, not build_signal outputs",
            "no SignalEngineV4, dispatch, Telegram, WebSocket, Sim101, or Live path was invoked",
            "do not treat this session as SHADOW vs REAL signal evidence without a future safe engine processor",
        ],
    }

    _write_json(session_dir / "session_metadata.json", summary)
    _write_json(session_dir / "session_summary.json", summary)
    (session_dir / "session_summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
    (session_dir / "server_console.log").write_text(
        "Historical playback audit-only feed processor completed without server, "
        "SignalEngineV4, dispatch, websocket, telegram, Sim101, or Live.\n",
        encoding="utf-8",
    )
    return session_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", type=Path, help="Existing logs/sessions/<id> directory from PR24")
    args = parser.parse_args(argv)

    session_dir = process_historical_playback_audit_only(args.session_dir)
    print(session_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
