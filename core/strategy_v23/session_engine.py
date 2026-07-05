from datetime import date, datetime, time, timedelta


def cme_session_date(timestamp: datetime) -> date:
    """Return the CME session end date (17:00 CT to 16:00 CT)."""
    return (timestamp + timedelta(days=1)).date() if timestamp.time() >= time(17) else timestamp.date()


def in_signal_window(timestamp: datetime, start: time, end: time) -> bool:
    return start <= timestamp.time() <= end

