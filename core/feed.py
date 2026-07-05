from core.candle import Candle
from core.delta import delta_calc


class Feed:
    """
    Feed PRO.
    Accepts only closed 1m candles.
    Stores rejection details for safe server logging.
    """

    def __init__(self):
        self.data = {"1m": []}
        self.last_rejection = None

    def normalize_bar_size(self, barSize):
        if isinstance(barSize, int):
            return barSize

        if isinstance(barSize, float) and barSize.is_integer():
            return int(barSize)

        if isinstance(barSize, str):
            barSize = barSize.lower().strip()

            if barSize.isdigit():
                return int(barSize)

            if barSize.endswith("m"):
                num = barSize.replace("m", "")
                if num.isdigit():
                    return int(num)

            if "minute" in barSize:
                num = barSize.replace("minute", "").strip()
                if num.isdigit():
                    return int(num)

        return None

    def _reject(self, reason, raw=None, field=None, expected=None, actual=None):
        self.last_rejection = {
            "reason": reason,
            "field": field,
            "expected": expected,
            "actual": actual,
            "barSize": None if raw is None else raw.get("barSize"),
            "instrument": None if raw is None else raw.get("instrument"),
            "timestamp": None if raw is None else raw.get("timestamp"),
            "isClosed": None if raw is None else raw.get("isClosed"),
        }
        return False

    def _coerce_float(self, raw, field):
        value = raw.get(field)
        try:
            raw[field] = float(value)
            return True
        except (TypeError, ValueError):
            self._reject(
                "invalid_numeric_field",
                raw,
                field=field,
                expected="number",
                actual=repr(value),
            )
            return False

    def _coerce_bool(self, raw, field):
        value = raw.get(field)
        if isinstance(value, bool):
            return True
        if isinstance(value, str):
            clean = value.strip().lower()
            if clean == "true":
                raw[field] = True
                return True
            if clean == "false":
                raw[field] = False
                return True

        self._reject(
            "invalid_bool_field",
            raw,
            field=field,
            expected="bool",
            actual=repr(value),
        )
        return False

    def push(self, raw):
        self.last_rejection = None

        if raw.get("barSize") is None:
            raw["barType"] = "Minute"
            raw["barSize"] = 1
            raw["isClosed"] = True

        required = ["open", "high", "low", "close", "volume", "timestamp"]
        for field in required:
            if field not in raw:
                return self._reject(
                    "missing_required_field",
                    raw,
                    field=field,
                    expected="present",
                    actual="missing",
                )

        for field in required:
            if not self._coerce_float(raw, field):
                return False

        if "isClosed" not in raw:
            raw["isClosed"] = True
        elif not self._coerce_bool(raw, "isClosed"):
            return False

        candle = Candle(raw)
        barSize = self.normalize_bar_size(candle.barSize)

        if barSize != 1:
            return self._reject(
                "unsupported_bar_size",
                raw,
                field="barSize",
                expected=1,
                actual=candle.barSize,
            )

        tf = "1m"
        buffer = self.data[tf]

        if not buffer:
            if candle.isClosed:
                candle.delta = delta_calc.compute_delta(candle)
                candle.prev_delta = 0.0
                candle.cumdelta = candle.delta

                buffer.append(candle)
                return True

            return self._reject(
                "first_bar_not_closed",
                raw,
                field="isClosed",
                expected=True,
                actual=candle.isClosed,
            )

        last = buffer[-1]

        if candle.timestamp == last.timestamp:
            if last.isClosed:
                return self._reject(
                    "duplicate_closed_timestamp",
                    raw,
                    field="timestamp",
                    expected="newer_than_last_closed",
                    actual=candle.timestamp,
                )

            last.high = max(last.high, candle.high)
            last.low = min(last.low, candle.low)
            last.close = candle.close
            last.volume += candle.volume
            last.isClosed = candle.isClosed

            last.delta = delta_calc.compute_delta(last)
            last.cumdelta = last.cumdelta

            return True

        if candle.timestamp > last.timestamp:
            if not candle.isClosed:
                return self._reject(
                    "new_bar_not_closed",
                    raw,
                    field="isClosed",
                    expected=True,
                    actual=candle.isClosed,
                )

            candle.delta = delta_calc.compute_delta(candle)
            candle.prev_delta = last.delta if last.delta is not None else 0.0
            candle.cumdelta = (last.cumdelta or 0.0) + candle.delta

            buffer.append(candle)

            if len(buffer) > 5000:
                self.data["1m"] = buffer[-2000:]

            return True

        return self._reject(
            "stale_or_out_of_order_timestamp",
            raw,
            field="timestamp",
            expected="greater_than_last_timestamp",
            actual=candle.timestamp,
        )

    def get_candles(self, timeframe):
        return self.data.get(timeframe, [])

    def get_tf(self, timeframe):
        return self.data.get(timeframe, [])
