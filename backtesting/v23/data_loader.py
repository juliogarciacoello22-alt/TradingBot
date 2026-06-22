from __future__ import annotations

import hashlib
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


@dataclass(frozen=True)
class GapAudit:
    previous_timestamp: datetime
    current_timestamp: datetime
    missing_minutes: int
    classification: str


def classify_gap(previous: datetime, current: datetime, max_short_gap_minutes: int) -> GapAudit | None:
    delta_seconds = (current - previous).total_seconds()
    if delta_seconds <= 60:
        return None
    missing_minutes = int(delta_seconds // 60) - 1
    # A new CME session begins at 17:00 CT. Requiring the first new bar to
    # arrive near that boundary prevents a missing intraday block from being
    # mislabeled as a maintenance, weekend, or holiday closure.
    at_session_open = (
        cme_session_date(previous) != cme_session_date(current)
        and previous.time() >= time(11, 0)
        and time(17, 0) <= current.time() <= time(17, 10)
    )
    if at_session_open:
        return GapAudit(previous, current, missing_minutes, "expected_session_closure")
    if missing_minutes <= max_short_gap_minutes:
        return GapAudit(previous, current, missing_minutes, "short_provider_gap")
    return GapAudit(previous, current, missing_minutes, "unexpected_long_gap")


def load_last_file(
    path: str | Path,
    *,
    timezone_name: str,
    tick_size: float,
    max_short_gap_minutes: int = 10,
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
            gap = classify_gap(previous, timestamp, max_short_gap_minutes)
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
    return LoadedDataset(source, digest, tuple(bars), tuple(gaps))
