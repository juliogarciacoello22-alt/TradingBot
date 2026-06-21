import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.strategy_v23.direction_engine import (
    BUY_ONLY_KINDS,
    SELL_ONLY_KINDS,
    classify_level,
    resolve_direction_conflicts,
    side_allowed,
    vwap_cross_direction,
)
from core.strategy_v23.models import Direction, Level, LevelDirection


class DirectionalityTests(unittest.TestCase):
    def test_strict_level_mapping(self):
        for kind in BUY_ONLY_KINDS:
            self.assertEqual(classify_level(kind), LevelDirection.BUY_ONLY)
        for kind in SELL_ONLY_KINDS:
            self.assertEqual(classify_level(kind), LevelDirection.SELL_ONLY)
        self.assertTrue(side_allowed(LevelDirection.BUY_ONLY, Direction.BUY))
        self.assertFalse(side_allowed(LevelDirection.BUY_ONLY, Direction.SELL))
        self.assertTrue(side_allowed(LevelDirection.SELL_ONLY, Direction.SELL))
        self.assertFalse(side_allowed(LevelDirection.SELL_ONLY, Direction.BUY))
        self.assertTrue(side_allowed(LevelDirection.NEUTRAL, Direction.BUY))
        self.assertTrue(side_allowed(LevelDirection.NEUTRAL, Direction.SELL))

    def test_vwap_cross_uses_previous_and_current_values(self):
        self.assertEqual(
            vwap_cross_direction(99, 100, 101, 100, LevelDirection.NEUTRAL),
            LevelDirection.BUY_ONLY,
        )
        self.assertEqual(
            vwap_cross_direction(101, 100, 99, 100, LevelDirection.BUY_ONLY),
            LevelDirection.SELL_ONLY,
        )

    def test_newer_opposing_level_wins_conflict(self):
        now = datetime(2025, 11, 4, tzinfo=ZoneInfo("America/Chicago"))
        old = Level("old", "prior_low", 99.75, 100.25, now, LevelDirection.BUY_ONLY)
        new = Level("new", "prior_high", 100.50, 101.0, now + timedelta(minutes=1), LevelDirection.SELL_ONLY)
        self.assertEqual(resolve_direction_conflicts([old, new], 1.0), {"old"})

    def test_fresher_level_wins_timestamp_tie(self):
        now = datetime(2025, 11, 4, tzinfo=ZoneInfo("America/Chicago"))
        tested = Level("tested", "prior_low", 99.75, 100.25, now, LevelDirection.BUY_ONLY, test_count=1)
        fresh = Level("fresh", "prior_high", 100.25, 100.75, now, LevelDirection.SELL_ONLY, test_count=0)
        self.assertEqual(resolve_direction_conflicts([tested, fresh], 1.0), {"tested"})


if __name__ == "__main__":
    unittest.main()

