from dataclasses import dataclass
from datetime import datetime


@dataclass
class HistoricalClock:
    current: datetime | None = None

    def advance(self, timestamp: datetime) -> None:
        if self.current is not None and timestamp <= self.current:
            raise ValueError("Historical clock cannot move backwards")
        self.current = timestamp

