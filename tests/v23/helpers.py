from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.strategy_v23.models import Bar


CHICAGO = ZoneInfo("America/Chicago")


def bar(minute: int, open_=100.0, high=101.0, low=99.0, close=100.5, volume=100.0):
    return Bar(
        datetime(2025, 11, 4, 8, 0, tzinfo=CHICAGO) + timedelta(minutes=minute),
        open_, high, low, close, volume,
    )

