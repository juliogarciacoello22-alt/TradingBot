import contextlib
import io
import unittest

from core.live_timestamp_validator import validate_bar_timestamp


class LiveTimestampValidatorTests(unittest.TestCase):
    NOW = 2_000_000_000.0

    def validate(self, timestamp, *, live=True, maximum=120):
        with contextlib.redirect_stdout(io.StringIO()):
            return validate_bar_timestamp(
                timestamp,
                live_mode=live,
                max_drift_seconds=maximum,
                now_utc=self.NOW,
            )

    def test_current_and_boundary_bars_are_accepted(self):
        self.assertTrue(self.validate(self.NOW - 60))
        self.assertTrue(self.validate(self.NOW - 120))
        self.assertTrue(self.validate(self.NOW + 120))

    def test_stale_and_future_bars_are_rejected(self):
        self.assertFalse(self.validate(self.NOW - 121))
        self.assertFalse(self.validate(self.NOW + 121))

    def test_invalid_timestamp_is_rejected(self):
        self.assertFalse(self.validate(None))
        self.assertFalse(self.validate("not-a-timestamp"))

    def test_playback_bypasses_wall_clock_validation(self):
        self.assertTrue(self.validate(1, live=False))


if __name__ == "__main__":
    unittest.main()

