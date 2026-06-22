import unittest
from datetime import datetime, timedelta

from backtesting.v23.metrics import calculate_metrics
from core.strategy_v23.models import Direction, Rejection, Setup
from core.strategy_v23.strategy_core import StrategyCoreV23
from core.strategy_v23.level_registry import LevelRegistry
from core.strategy_v23.price_math import round_to_tick

from .helpers import CHICAGO, bar


class CoreInvariantTests(unittest.TestCase):
    def test_tick_rounding_is_identical_across_components(self):
        core = StrategyCoreV23()
        registry = LevelRegistry(0.25)
        self.assertEqual(round_to_tick(100.125, 0.25), 100.25)
        self.assertEqual(core.tick(100.125), 100.25)
        self.assertEqual(registry.tick(100.125), 100.25)

    def test_setup_expires_on_exact_tenth_bar(self):
        core = StrategyCoreV23()
        level = core.levels.add("prior_low", 99.75, 100.25, bar(0).timestamp)
        setup = Setup(
            level_id=level.identifier,
            level_kind=level.kind,
            level_direction=level.direction,
            lower=level.lower,
            upper=level.upper,
            side=Direction.BUY,
            touched_bar_index=0,
            event_bar_index=0,
            event_extreme=99.0,
            event_type="sweep",
        )
        core.setups[(level.identifier, Direction.BUY)] = setup

        self.assertEqual(core._advance_setups(bar(9, close=100.0), 9), [])
        self.assertIn((level.identifier, Direction.BUY), core.setups)
        self.assertEqual(core._advance_setups(bar(10, close=100.0), 10), [])
        self.assertNotIn((level.identifier, Direction.BUY), core.setups)
        self.assertEqual(core.rejections[-1].reason, "setup_expired")

    def test_new_cme_session_resets_dynamic_vwap_state(self):
        core = StrategyCoreV23()
        core.process_bar(bar(0))
        first_vwap = core.levels.get("dynamic:vwap")
        self.assertIsNotNone(first_vwap)
        first_created_at = first_vwap.created_at

        next_session = bar(0).__class__(
            datetime(2025, 11, 4, 17, 0, tzinfo=CHICAGO),
            110.0, 111.0, 109.0, 110.5, 100.0,
        )
        core.process_bar(next_session)
        reset_vwap = core.levels.get("dynamic:vwap")

        self.assertIsNotNone(reset_vwap)
        self.assertNotEqual(reset_vwap.created_at, first_created_at)
        self.assertEqual(reset_vwap.created_at, next_session.timestamp)

    def test_only_current_session_open_and_prior_levels_remain_active(self):
        core = StrategyCoreV23()
        start = datetime(2025, 11, 3, 17, 0, tzinfo=CHICAGO)
        for day in range(3):
            timestamp = start + timedelta(days=day)
            core.process_bar(bar(0).__class__(
                timestamp,
                100.0 + day,
                101.0 + day,
                99.0 + day,
                100.5 + day,
                100.0,
            ))

        active = core.levels.active()
        self.assertEqual(sum(level.kind == "cme_open" for level in active), 1)
        self.assertEqual(sum(level.kind == "prior_high" for level in active), 1)
        self.assertEqual(sum(level.kind == "prior_low" for level in active), 1)

    def test_dynamic_vwap_recovers_from_invalid_state(self):
        registry = LevelRegistry(0.25)
        first = bar(0).timestamp
        level = registry.update_dynamic("vwap", 100.0, first)
        level.test_count = 3
        level.state = level.state.INVALID
        level.active = False

        updated = registry.update_dynamic("vwap", 100.0, first + timedelta(minutes=1))

        self.assertTrue(updated.active)
        self.assertEqual(updated.state.value, "fresh")
        self.assertEqual(updated.test_count, 0)
        self.assertEqual(updated.created_at, first + timedelta(minutes=1))

    def test_daily_metrics_include_zero_trade_days_and_rejections(self):
        rejection = Rejection(bar(0).timestamp, "outside_signal_window")
        summary, daily, curve = calculate_metrics(
            [],
            statistics_start_date="2025-11-04",
            all_dates=["2025-11-04", "2025-11-05"],
            rejections=[rejection],
        )

        self.assertEqual(summary["trades"], 0)
        self.assertEqual(curve, [])
        self.assertEqual([row["date"] for row in daily], ["2025-11-04", "2025-11-05"])
        self.assertEqual(daily[0]["rejections"], {"outside_signal_window": 1})
        self.assertEqual(daily[1]["trades"], 0)


if __name__ == "__main__":
    unittest.main()
