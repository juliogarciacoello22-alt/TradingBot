from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_v23.models import Bar
from core.strategy_v23.session_engine import cme_session_date


LINE_PATTERN = re.compile(
    r"^(\d{8} \d{6});(-?\d+(?:\.\d+)?);(-?\d+(?:\.\d+)?);"
    r"(-?\d+(?:\.\d+)?);(-?\d+(?:\.\d+)?);(\d+(?:\.\d+)?)$"
)


@dataclass(frozen=True)
class LoadedDataset:
    path: Path
    sha256: str
    bars: tuple[Bar, ...]
    gaps: tuple["GapAudit", ...] = ()
    closure_calendar_sha256: str | None = None


@dataclass(frozen=True)
class GapAudit:
    previous_timestamp: datetime
    current_timestamp: datetime
    missing_minutes: int
    classification: str


@dataclass(frozen=True)
class ExpectedClosure:
    last_bar_timestamp: datetime
    next_bar_timestamp: datetime
    label: str


@dataclass(frozen=True)
class ClosureCalendar:
    path: Path
    sha256: str
    closures: tuple[ExpectedClosure, ...]


def load_expected_closures(path: str | Path, *, timezone_name: str) -> ClosureCalendar:
    timezone = ZoneInfo(timezone_name)
    source = Path(path).resolve()
    raw = source.read_bytes()
    records = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(records, list):
        raise ValueError("Closure calendar must be a JSON list")
    closures = []
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict) or not {"last_bar", "next_bar", "label"} <= record.keys():
            raise ValueError(f"Invalid closure calendar record {index}")
        last_bar = datetime.fromisoformat(str(record["last_bar"]))
        next_bar = datetime.fromisoformat(str(record["next_bar"]))
        last_bar = last_bar.replace(tzinfo=timezone) if last_bar.tzinfo is None else last_bar.astimezone(timezone)
        next_bar = next_bar.replace(tzinfo=timezone) if next_bar.tzinfo is None else next_bar.astimezone(timezone)
        if next_bar <= last_bar:
            raise ValueError(f"Closure calendar record {index} is not increasing")
        closures.append(ExpectedClosure(last_bar, next_bar, str(record["label"])))
    return ClosureCalendar(source, hashlib.sha256(raw).hexdigest().upper(), tuple(closures))


def classify_gap(
    previous: datetime,
    current: datetime,
    max_short_gap_minutes: int,
    expected_closures: tuple[ExpectedClosure, ...] = (),
) -> GapAudit | None:
    delta_seconds = (current - previous).total_seconds()
    if delta_seconds <= 60:
        return None
    missing_minutes = int(delta_seconds // 60) - 1
    exact_close = previous.time() == time(15, 59)
    exact_open = current.time() == time(17, 0)
    daily_maintenance = (
        previous.date() == current.date()
        and cme_session_date(previous) != cme_session_date(current)
        and exact_close
        and exact_open
    )
    if daily_maintenance:
        return GapAudit(previous, current, missing_minutes, "daily_maintenance")
    weekend = (
        previous.weekday() == 4
        and current.weekday() == 6
        and (current.date() - previous.date()).days == 2
        and exact_close
        and exact_open
    )
    if weekend:
        return GapAudit(previous, current, missing_minutes, "weekend_closure")
    for closure in expected_closures:
        if previous == closure.last_bar_timestamp and current == closure.next_bar_timestamp:
            return GapAudit(previous, current, missing_minutes, f"calendar:{closure.label}")
    if missing_minutes <= max_short_gap_minutes:
        return GapAudit(previous, current, missing_minutes, "short_provider_gap")
    return GapAudit(previous, current, missing_minutes, "unexpected_long_gap")


def load_last_file(
    path: str | Path,
    *,
    timezone_name: str,
    tick_size: float,
    max_short_gap_minutes: int = 10,
    closure_calendar: ClosureCalendar | None = None,
) -> LoadedDataset:
    source = Path(path).resolve()
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest().upper()
    timezone = ZoneInfo(timezone_name)
    bars: list[Bar] = []
    gaps: list[GapAudit] = []
    previous = None
    for line_number, text in enumerate(raw.decode("utf-8-sig").splitlines(), start=1):
        match = LINE_PATTERN.fullmatch(text.strip())
        if not match:
            raise ValueError(f"Invalid NinjaTrader row at line {line_number}")
        timestamp = datetime.strptime(match.group(1), "%Y%m%d %H%M%S").replace(tzinfo=timezone)
        values = [float(match.group(index)) for index in range(2, 7)]
        open_, high, low, close, volume = values
        if previous is not None and timestamp <= previous:
            raise ValueError(f"Timestamps are not strictly increasing at line {line_number}")
        if previous is not None:
            gap = classify_gap(
                previous,
                timestamp,
                max_short_gap_minutes,
                closure_calendar.closures if closure_calendar else (),
            )
            if gap is not None:
                if gap.classification == "unexpected_long_gap":
                    raise ValueError(
                        f"Unexpected {gap.missing_minutes}-minute gap before line {line_number}: "
                        f"{previous.isoformat()} -> {timestamp.isoformat()}"
                    )
                gaps.append(gap)
        if not (low <= open_ <= high and low <= close <= high and volume >= 0):
            raise ValueError(f"Invalid OHLCV at line {line_number}")
        if any(abs(round(price / tick_size) * tick_size - price) > 1e-9 for price in (open_, high, low, close)):
            raise ValueError(f"Price off tick at line {line_number}")
        bars.append(Bar(timestamp, open_, high, low, close, volume))
        previous = timestamp
    if not bars:
        raise ValueError("Dataset is empty")
    return LoadedDataset(
        source,
        digest,
        tuple(bars),
        tuple(gaps),
        closure_calendar.sha256 if closure_calendar else None,
    )
