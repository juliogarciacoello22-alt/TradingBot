import time
from datetime import datetime, timezone


def validate_bar_timestamp(
    bar_timestamp,
    *,
    live_mode: bool,
    max_drift_seconds: float,
    now_utc: float | None = None,
) -> bool:
    """Reject stale/future bars in live mode without affecting replay."""
    if not live_mode:
        return True

    try:
        timestamp = float(bar_timestamp)
    except (TypeError, ValueError):
        print("===== BAR REJECTED - INVALID TIMESTAMP =====")
        print(f"Raw timestamp: {bar_timestamp!r}")
        print("Reason: timestamp is missing or not numeric. Pipeline not executed.")
        print("============================================")
        return False

    now = time.time() if now_utc is None else float(now_utc)
    drift = now - timestamp
    if abs(drift) <= max_drift_seconds:
        return True

    try:
        bar_time = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        bar_time = f"invalid ({timestamp})"
    current_time = datetime.fromtimestamp(now, tz=timezone.utc).isoformat()
    direction = "stale" if drift > 0 else "future"

    print("===== BAR REJECTED - INVALID TIMESTAMP =====")
    print(f"Bar timestamp: {bar_time}")
    print(f"Current time:  {current_time}")
    print(f"Difference: {abs(drift):.2f}s (maximum {max_drift_seconds}s)")
    print(f"Reason: {direction} bar. Pipeline not executed.")
    print("============================================")
    return False
