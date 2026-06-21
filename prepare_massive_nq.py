from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
TICK = 0.25


def fmt_price(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Massive NQ minute aggregates")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--ticker", default="NQH6")
    parser.add_argument("--continuous-root")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-rows-per-session", type=int, default=1000)
    args = parser.parse_args()

    rows_by_ts: dict[int, dict] = {}
    candidate_records = []
    duplicate_rows = 0
    conflicting_duplicates = []
    source_counts = Counter()
    ticker_counts = Counter()

    for path in sorted(args.inputs):
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            required = {"ticker", "session_end_date", "window_start", "open", "high", "low", "close", "volume"}
            missing = required.difference(reader.fieldnames or [])
            if missing:
                raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
            for raw in reader:
                ticker_counts[raw["ticker"]] += 1
                if args.continuous_root:
                    if not re.match(rf"^{re.escape(args.continuous_root)}[HMUZ]\d{{1,2}}$", raw["ticker"]):
                        continue
                elif raw["ticker"] != args.ticker:
                    continue
                ts_ns = int(raw["window_start"])
                record = {
                    "timestamp_ns": ts_ns,
                    "session_end_date": raw["session_end_date"],
                    "open": float(raw["open"]),
                    "high": float(raw["high"]),
                    "low": float(raw["low"]),
                    "close": float(raw["close"]),
                    "volume": int(float(raw["volume"])),
                    "source": path.name,
                    "ticker": raw["ticker"],
                }
                candidate_records.append(record)

    contract_by_session = {}
    if args.continuous_root:
        contract_stats = defaultdict(lambda: defaultdict(lambda: {"rows": 0, "volume": 0}))
        for record in candidate_records:
            stats = contract_stats[record["session_end_date"]][record["ticker"]]
            stats["rows"] += 1
            stats["volume"] += record["volume"]
        for session_date, contracts in contract_stats.items():
            contract_by_session[session_date] = max(
                contracts,
                key=lambda ticker: (contracts[ticker]["volume"], contracts[ticker]["rows"], ticker),
            )
        selected_records = [r for r in candidate_records
                            if r["ticker"] == contract_by_session[r["session_end_date"]]]
    else:
        selected_records = candidate_records

    for record in selected_records:
                ts_ns = record["timestamp_ns"]
                if ts_ns in rows_by_ts:
                    duplicate_rows += 1
                    old = rows_by_ts[ts_ns]
                    fields = ("open", "high", "low", "close", "volume")
                    if any(old[k] != record[k] for k in fields):
                        conflicting_duplicates.append(ts_ns)
                    continue
                rows_by_ts[ts_ns] = record
                source_counts[record["source"]] += 1

    rows = [rows_by_ts[k] for k in sorted(rows_by_ts)]
    if not rows:
        raise ValueError(f"No rows found for ticker {args.continuous_root or args.ticker}")

    sessions = defaultdict(list)
    for row in rows:
        sessions[row["session_end_date"]].append(row)

    excluded_incomplete_sessions = {
        session_date: len(session_rows)
        for session_date, session_rows in sessions.items()
        if len(session_rows) < args.min_rows_per_session
    }
    if excluded_incomplete_sessions:
        rows = [row for row in rows if row["session_end_date"] not in excluded_incomplete_sessions]
        sessions = defaultdict(list)
        for row in rows:
            sessions[row["session_end_date"]].append(row)
    if not rows:
        raise ValueError("All selected sessions were incomplete")

    invalid_ohlc = []
    invalid_tick = []
    for row in rows:
        if not (row["low"] <= row["open"] <= row["high"] and
                row["low"] <= row["close"] <= row["high"] and row["volume"] >= 0):
            invalid_ohlc.append(row["timestamp_ns"])
        if any(abs(round(row[k] / TICK) * TICK - row[k]) > 1e-9 for k in ("open", "high", "low", "close")):
            invalid_tick.append(row["timestamp_ns"])

    gaps = []
    for session_date, session_rows in sorted(sessions.items()):
        for left, right in zip(session_rows, session_rows[1:]):
            delta_minutes = (right["timestamp_ns"] - left["timestamp_ns"]) / 60_000_000_000
            if delta_minutes != 1:
                gaps.append({
                    "session_end_date": session_date,
                    "after_timestamp_ns": left["timestamp_ns"],
                    "before_timestamp_ns": right["timestamp_ns"],
                    "missing_minutes": int(delta_minutes - 1),
                })

    args.output_dir.mkdir(parents=True, exist_ok=True)
    first_session, last_session = min(sessions), max(sessions)
    stem = f"NQ_1min_{first_session}_{last_session}"
    master_path = args.output_dir / f"{stem}.csv"
    ninja_path = args.output_dir / f"{stem}.Last.txt"
    report_path = args.output_dir / f"{stem}_validation.json"

    with master_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for row in rows:
            dt = datetime.fromtimestamp(row["timestamp_ns"] / 1e9, timezone.utc).astimezone(CHICAGO)
            writer.writerow([dt.isoformat(), fmt_price(row["open"]), fmt_price(row["high"]),
                             fmt_price(row["low"]), fmt_price(row["close"]), row["volume"]])

    with ninja_path.open("w", encoding="utf-8", newline="") as fh:
        for row in rows:
            dt = datetime.fromtimestamp(row["timestamp_ns"] / 1e9, timezone.utc).astimezone(CHICAGO)
            fh.write(";".join([dt.strftime("%Y%m%d %H%M%S"), fmt_price(row["open"]),
                               fmt_price(row["high"]), fmt_price(row["low"]),
                               fmt_price(row["close"]), str(row["volume"])]) + "\n")

    report = {
        "ticker": args.continuous_root or args.ticker,
        "continuous": bool(args.continuous_root),
        "contract_by_session": dict(sorted(contract_by_session.items())),
        "timezone": "America/Chicago",
        "source_files": [str(p) for p in sorted(args.inputs)],
        "source_rows_selected": dict(source_counts),
        "output_rows": len(rows),
        "session_end_dates": sorted(sessions),
        "rows_per_session": {k: len(v) for k, v in sorted(sessions.items())},
        "excluded_incomplete_sessions": excluded_incomplete_sessions,
        "first_timestamp": datetime.fromtimestamp(rows[0]["timestamp_ns"] / 1e9, timezone.utc).astimezone(CHICAGO).isoformat(),
        "last_timestamp": datetime.fromtimestamp(rows[-1]["timestamp_ns"] / 1e9, timezone.utc).astimezone(CHICAGO).isoformat(),
        "duplicates_removed": duplicate_rows,
        "conflicting_duplicates": len(conflicting_duplicates),
        "invalid_ohlc_rows": len(invalid_ohlc),
        "invalid_tick_rows": len(invalid_tick),
        "unexpected_intrasession_gaps": gaps,
        "outputs": {"master_csv": str(master_path), "ninjatrader": str(ninja_path)},
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
