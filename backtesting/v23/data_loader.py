from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.strategy_v23.models import Bar


LINE_PATTERN = re.compile(
    r"^(\d{8} \d{6});(-?\d+(?:\.\d+)?);(-?\d+(?:\.\d+)?);"
    r"(-?\d+(?:\.\d+)?);(-?\d+(?:\.\d+)?);(\d+(?:\.\d+)?)$"
)


@dataclass(frozen=True)
class LoadedDataset:
    path: Path
    sha256: str
    bars: tuple[Bar, ...]


def load_last_file(path: str | Path, *, timezone_name: str, tick_size: float) -> LoadedDataset:
    source = Path(path).resolve()
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest().upper()
    timezone = ZoneInfo(timezone_name)
    bars: list[Bar] = []
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
        if not (low <= open_ <= high and low <= close <= high and volume >= 0):
            raise ValueError(f"Invalid OHLCV at line {line_number}")
        if any(abs(round(price / tick_size) * tick_size - price) > 1e-9 for price in (open_, high, low, close)):
            raise ValueError(f"Price off tick at line {line_number}")
        bars.append(Bar(timestamp, open_, high, low, close, volume))
        previous = timestamp
    if not bars:
        raise ValueError("Dataset is empty")
    return LoadedDataset(source, digest, tuple(bars))

