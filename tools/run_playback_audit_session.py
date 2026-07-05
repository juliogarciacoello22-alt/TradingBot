"""Generate a synthetic PLAYBACK audit session for SHADOW vs REAL analysis.

This runner is intentionally fixture-based and audit-only. It does not import
server.py, instantiate the live pipeline, open WebSockets, load .env, send
Telegram messages, or call dispatch/send_signal. The generated JSONL files use
the same artifact shape consumed by tools/audit_shadow_vs_real_post_pr19.py.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_FILES = (
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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_session_id(now: datetime | None = None) -> str:
    return (now or _utc_now()).astimezone().strftime("playback_audit_%Y%m%d_%H%M%S")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _ensure_empty_artifacts(session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_FILES:
        path = session_dir / name
        if path.suffix == ".json":
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.write_text("", encoding="utf-8")


def _fixture_rows(session_id: str) -> dict[str, list[dict[str, Any]]]:
    base_ts = 1782490860
    return {
        "feed_events.jsonl": [
            {
                "event": "feed_event",
                "session_id": session_id,
                "timestamp": base_ts,
                "feed_accepted": True,
                "pipeline_executed": True,
                "source": "synthetic_playback_fixture",
                "run_mode": "PLAYBACK_AUDIT",
            },
            {
                "event": "feed_event",
                "session_id": session_id,
                "timestamp": base_ts + 60,
                "feed_accepted": True,
                "pipeline_executed": True,
                "source": "synthetic_playback_fixture",
                "run_mode": "PLAYBACK_AUDIT",
            },
        ],
        "pipeline_decisions.jsonl": [
            {
                "event": "pipeline_decision",
                "session_id": session_id,
                "timestamp": base_ts,
                "final_decision": "NO_TRADE",
                "final_reason": "valid_entry_failed",
                "detail": "shadow_would_unlock_but_real_valid_entry_blocked",
                "audit_only": True,
                "dispatch_attempted": False,
            },
            {
                "event": "pipeline_decision",
                "session_id": session_id,
                "timestamp": base_ts + 60,
                "final_decision": "NO_DISPATCH",
                "final_reason": "playback_audit_no_dispatch",
                "detail": "real_signal_generated_but_runner_never_dispatches",
                "audit_only": True,
                "dispatch_attempted": False,
            },
        ],
        "signal_engine_full_path_snapshots.jsonl": [
            {
                "event": "signal_engine_v4_full_path_snapshot",
                "snapshot": {
                    "decision_id": f"{session_id}|{base_ts}",
                    "timestamp": base_ts,
                    "microstructure": {
                        "displacement": "up",
                        "momentum": "up",
                        "fake_displacement": False,
                        "inducement": None,
                        "mitigation_light": True,
                        "mitigation_light_reason": "synthetic_overlap_fixture",
                        "mitigation_light_v2": False,
                        "mitigation_contamination": False,
                        "mitigation_contamination_reason": "not_contaminated_fixture",
                        "ob": {"side": "BUY", "strength": 3, "source": "synthetic_fixture"},
                    },
                    "timing": {"valid": True, "session": "playback_fixture"},
                    "delta": 125.0,
                    "last_candle": {
                        "open": 100.0,
                        "high": 101.25,
                        "low": 99.75,
                        "close": 100.75,
                        "volume": 1000,
                        "timestamp": base_ts,
                    },
                    "tf": {"1m": [{"timestamp": base_ts, "close": 100.75}], "5m": [], "30m": []},
                    "context": {"trend_4h": "bullish"},
                    "forecast": {"source": "synthetic_fixture"},
                    "price": 100.75,
                    "stage_outputs": {
                        "signal_engine": {
                            "last_valid_entry_reason": "mitigation_light_true",
                            "last_build_signal_reason": "valid_entry_failed",
                            "last_valid_entry_shadow": {
                                "valid_entry_shadow_without_mitigation_v1": True,
                                "would_pass_valid_entry_without_v1": True,
                                "valid_entry_shadow_v2_mitigation": False,
                                "would_block_by_v2_contamination": False,
                                "valid_entry_ab_delta": "shadow_would_unlock",
                                "valid_entry_ab_shadow_would_unlock": True,
                            },
                            "signal_is_none": True,
                        }
                    },
                    "missing_fields": [],
                },
            },
            {
                "event": "signal_engine_v4_full_path_snapshot",
                "snapshot": {
                    "decision_id": f"{session_id}|{base_ts + 60}",
                    "timestamp": base_ts + 60,
                    "microstructure": {
                        "displacement": "down",
                        "momentum": "down",
                        "fake_displacement": False,
                        "inducement": None,
                        "mitigation_light": False,
                        "mitigation_light_reason": None,
                        "mitigation_light_v2": False,
                        "mitigation_contamination": False,
                        "mitigation_contamination_reason": None,
                        "ob": {"side": "SELL", "strength": 4, "source": "synthetic_fixture"},
                    },
                    "timing": {"valid": True, "session": "playback_fixture"},
                    "delta": -140.0,
                    "last_candle": {
                        "open": 100.75,
                        "high": 101.0,
                        "low": 99.25,
                        "close": 99.5,
                        "volume": 1100,
                        "timestamp": base_ts + 60,
                    },
                    "tf": {"1m": [{"timestamp": base_ts + 60, "close": 99.5}], "5m": [], "30m": []},
                    "context": {"trend_4h": "bearish"},
                    "forecast": {"source": "synthetic_fixture"},
                    "price": 99.5,
                    "stage_outputs": {
                        "signal_engine": {
                            "last_valid_entry_reason": "entry_filters_passed",
                            "last_build_signal_reason": "scalper_generated",
                            "last_valid_entry_shadow": {
                                "valid_entry_ab_delta": None,
                                "valid_entry_ab_shadow_would_unlock": False,
                            },
                            "signal_is_none": False,
                        }
                    },
                    "missing_fields": [],
                },
            },
        ],
        "signal_candidates.jsonl": [
            {
                "event": "signal_candidate",
                "session_id": session_id,
                "timestamp": base_ts + 60,
                "side": "SELL",
                "mode": "SCALPER",
                "audit_only": True,
                "source": "synthetic_playback_fixture",
            }
        ],
        "signals_enriched.jsonl": [
            {
                "event": "signal_enriched",
                "session_id": session_id,
                "timestamp": base_ts + 60,
                "side": "SELL",
                "entry": 99.5,
                "stop": 100.5,
                "tp1": 98.5,
                "tp2": 97.5,
                "tp3": 96.5,
                "dispatch_status": "blocked_by_playback_audit_runner",
                "audit_only": True,
            }
        ],
        "dispatch_events.jsonl": [
            {
                "event": "dispatch_event",
                "session_id": session_id,
                "timestamp": base_ts + 60,
                "allowed": False,
                "reason": "playback_audit_no_dispatch",
                "dispatch_status": "not_attempted",
                "send_signal_called": False,
                "audit_only": True,
            }
        ],
        "telegram_events.jsonl": [
            {
                "event": "telegram_event",
                "session_id": session_id,
                "timestamp": base_ts + 60,
                "sent": False,
                "reason": "telegram_disabled_by_playback_audit_runner",
                "audit_only": True,
            }
        ],
        "missed_trade_candidates.jsonl": [
            {
                "event": "missed_trade_candidate",
                "session_id": session_id,
                "timestamp": base_ts,
                "classification": "possible_false_negative_pending_review",
                "primary_block": "mitigation_light_true",
                "audit_only": True,
            }
        ],
    }


def _summary(session_id: str, session_dir: Path) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "session_dir": str(session_dir),
        "mode": "PLAYBACK_AUDIT",
        "audit_only": True,
        "synthetic_fixture_based": True,
        "server_imported": False,
        "pipeline_live_imported": False,
        "send_signal_called": False,
        "websocket_opened": False,
        "telegram_enabled": False,
        "real_or_sim_account_required": False,
        "orders_sent": 0,
        "notes": [
            "Generated artifacts are for SHADOW vs REAL audit parser validation.",
            "This is not a trading simulation and not evidence of real execution.",
        ],
    }


def create_playback_audit_session(
    *,
    logs_root: Path | None = None,
    session_id: str | None = None,
) -> Path:
    root = Path(logs_root) if logs_root is not None else _project_root() / "logs" / "sessions"
    resolved_session_id = session_id or _default_session_id()
    session_dir = root / resolved_session_id

    _ensure_empty_artifacts(session_dir)
    rows_by_file = _fixture_rows(resolved_session_id)
    for filename, rows in rows_by_file.items():
        _jsonl_write(session_dir / filename, rows)

    summary = _summary(resolved_session_id, session_dir)
    (session_dir / "session_metadata.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (session_dir / "session_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (session_dir / "session_summary.md").write_text(
        "\n".join(
            [
                "# PLAYBACK Audit Session",
                "",
                f"- session_id: `{resolved_session_id}`",
                "- mode: `PLAYBACK_AUDIT`",
                "- audit_only: `true`",
                "- synthetic_fixture_based: `true`",
                "- send_signal_called: `false`",
                "- websocket_opened: `false`",
                "- telegram_enabled: `false`",
                "- orders_sent: `0`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (session_dir / "server_console.log").write_text(
        "PLAYBACK_AUDIT fixture session generated without server, dispatch, websocket, or telegram.\n",
        encoding="utf-8",
    )
    return session_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs-root", type=Path, help="Defaults to logs/sessions under the project root")
    parser.add_argument("--session-id", help="Optional deterministic session id")
    args = parser.parse_args(argv)

    session_dir = create_playback_audit_session(logs_root=args.logs_root, session_id=args.session_id)
    print(session_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
