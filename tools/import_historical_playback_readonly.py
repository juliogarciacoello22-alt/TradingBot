"""Import historical/playback bars into a read-only audit session.

The importer reads a local CSV, JSON, JSONL, or NinjaTrader .Last.txt file and
writes audit artifacts under logs/sessions/<session_id>. It does not import
server.py, instantiate live engines, open WebSockets, load .env, call
send_signal, or produce pipeline/build-signal/SHADOW results.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


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


@dataclass(frozen=True)
class HistoricalBar:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_session_id(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone().strftime("historical_playback_%Y%m%d_%H%M%S")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _to_float(record: dict[str, Any], key: str) -> float:
    try:
        return float(record[key])
    except KeyError as exc:
        raise ValueError(f"Missing required field: {key}") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid numeric field {key}: {record.get(key)!r}") from exc


def _validate_bar(bar: HistoricalBar, index: int) -> HistoricalBar:
    if not bar.timestamp:
        raise ValueError(f"Missing timestamp at row {index}")
    if not (bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high):
        raise ValueError(f"Invalid OHLC range at row {index}")
    if bar.volume < 0:
        raise ValueError(f"Invalid negative volume at row {index}")
    return bar


def _bar_from_mapping(record: dict[str, Any], index: int) -> HistoricalBar:
    timestamp = str(record.get("timestamp") or record.get("time") or record.get("datetime") or "")
    bar = HistoricalBar(
        timestamp=timestamp,
        open=_to_float(record, "open"),
        high=_to_float(record, "high"),
        low=_to_float(record, "low"),
        close=_to_float(record, "close"),
        volume=_to_float(record, "volume"),
    )
    return _validate_bar(bar, index)


def _load_csv(path: Path) -> list[HistoricalBar]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("CSV input has no header")
        rows = [_bar_from_mapping(record, index) for index, record in enumerate(reader, start=1)]
    if not rows:
        raise ValueError("Input dataset is empty")
    return rows


def _load_json(path: Path) -> list[HistoricalBar]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("JSON input must be a list of bar objects")
    rows = []
    for index, record in enumerate(payload, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"JSON row {index} is not an object")
        rows.append(_bar_from_mapping(record, index))
    if not rows:
        raise ValueError("Input dataset is empty")
    return rows


def _load_jsonl(path: Path) -> list[HistoricalBar]:
    rows = []
    for index, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"JSONL row {index} is not an object")
        rows.append(_bar_from_mapping(record, index))
    if not rows:
        raise ValueError("Input dataset is empty")
    return rows


def _load_last(path: Path) -> list[HistoricalBar]:
    rows = []
    for index, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(";")
        if len(parts) != 6:
            raise ValueError(f"Invalid NinjaTrader .Last row at line {index}")
        record = {
            "timestamp": parts[0],
            "open": parts[1],
            "high": parts[2],
            "low": parts[3],
            "close": parts[4],
            "volume": parts[5],
        }
        rows.append(_bar_from_mapping(record, index))
    if not rows:
        raise ValueError("Input dataset is empty")
    return rows


def load_bars(path: Path, input_format: str | None = None) -> list[HistoricalBar]:
    source = Path(path)
    fmt = (input_format or source.suffix.lower().lstrip(".")).lower()
    if fmt == "csv":
        return _load_csv(source)
    if fmt == "json":
        return _load_json(source)
    if fmt == "jsonl":
        return _load_jsonl(source)
    if fmt in {"txt", "last"}:
        return _load_last(source)
    raise ValueError(f"Unsupported input format: {fmt}")


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _ensure_artifact_files(session_dir: Path) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_FILES:
        path = session_dir / name
        if path.suffix == ".json":
            path.write_text("{}\n", encoding="utf-8")
        else:
            path.write_text("", encoding="utf-8")


def import_historical_playback(
    source_path: Path,
    *,
    logs_root: Path | None = None,
    session_id: str | None = None,
    input_format: str | None = None,
    timezone_name: str = "America/Chicago",
    synthetic_fixture_based: bool = False,
) -> Path:
    source = Path(source_path).resolve()
    bars = load_bars(source, input_format)
    digest = _sha256(source)
    root = Path(logs_root) if logs_root is not None else _project_root() / "logs" / "sessions"
    resolved_session_id = session_id or _default_session_id()
    session_dir = root / resolved_session_id

    _ensure_artifact_files(session_dir)

    feed_events = [
        {
            "event": "feed_event",
            "session_id": resolved_session_id,
            "sequence": index,
            "timestamp": bar.timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "feed_accepted": True,
            "pipeline_executed": False,
            "source_type": "historical_playback",
            "synthetic_fixture_based": synthetic_fixture_based,
            "no_dispatch": True,
            "no_live": True,
        }
        for index, bar in enumerate(bars, start=1)
    ]
    _write_jsonl(session_dir / "feed_events.jsonl", feed_events)

    metadata = {
        "session_id": resolved_session_id,
        "source_type": "historical_playback",
        "source_path": str(source),
        "source_sha256": digest,
        "input_format": input_format or source.suffix.lower().lstrip("."),
        "row_count": len(bars),
        "first_timestamp": bars[0].timestamp,
        "last_timestamp": bars[-1].timestamp,
        "timezone": timezone_name,
        "synthetic_fixture_based": synthetic_fixture_based,
        "no_dispatch": True,
        "no_live": True,
        "server_imported": False,
        "pipeline_live_imported": False,
        "pipeline_processed": False,
        "send_signal_called": False,
        "websocket_opened": False,
        "telegram_enabled": False,
        "orders_sent": 0,
        "notes": [
            "Historical/playback bars were imported as feed artifacts only.",
            "No pipeline decisions, build_signal results, dispatch events, or SHADOW metrics were generated.",
        ],
    }
    (session_dir / "session_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (session_dir / "session_summary.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (session_dir / "session_summary.md").write_text(
        "\n".join(
            [
                "# Historical Playback Import",
                "",
                f"- session_id: `{resolved_session_id}`",
                "- source_type: `historical_playback`",
                f"- row_count: `{len(bars)}`",
                f"- source_sha256: `{digest}`",
                f"- synthetic_fixture_based: `{str(synthetic_fixture_based).lower()}`",
                "- no_dispatch: `true`",
                "- no_live: `true`",
                "- pipeline_processed: `false`",
                "",
                "This session imports feed artifacts only. It does not contain",
                "pipeline decisions, full-path snapshots, dispatch events, or",
                "SHADOW vs REAL metrics.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (session_dir / "server_console.log").write_text(
        "Historical playback import completed without server, pipeline, dispatch, websocket, or telegram.\n",
        encoding="utf-8",
    )
    return session_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_path", type=Path)
    parser.add_argument("--logs-root", type=Path)
    parser.add_argument("--session-id")
    parser.add_argument("--input-format", choices=("csv", "json", "jsonl", "txt", "last"))
    parser.add_argument("--timezone", default="America/Chicago")
    parser.add_argument("--synthetic-fixture", action="store_true")
    args = parser.parse_args(argv)

    session_dir = import_historical_playback(
        args.source_path,
        logs_root=args.logs_root,
        session_id=args.session_id,
        input_format=args.input_format,
        timezone_name=args.timezone,
        synthetic_fixture_based=args.synthetic_fixture,
    )
    print(session_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
