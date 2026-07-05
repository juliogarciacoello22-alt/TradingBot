import unittest

from core.strategy_v23.models import Direction, Level, LevelDirection
from core.strategy_v23.setup_state_machine import advance_setup, start_setup

from .helpers import bar


class StateMachineTests(unittest.TestCase):
    def test_buy_rejection_requires_two_closes_above(self):
        level = Level("level", "prior_low", 99.75, 100.25, bar(0).timestamp, LevelDirection.BUY_ONLY)
        event = bar(0, open_=100.0, high=100.5, low=98.0, close=100.0)
        setup = start_setup(event, level, Direction.BUY, 0, 0.25, 0.40)
        self.assertIsNotNone(setup)
        state, ready = advance_setup(setup, bar(1, close=100.5))
        self.assertEqual((state, ready), ("active", False))
        state, ready = advance_setup(setup, bar(2, close=100.75))
        self.assertEqual((state, ready), ("ready", True))

    def test_two_opposite_closes_invalidate(self):
        level = Level("level", "prior_low", 99.75, 100.25, bar(0).timestamp, LevelDirection.BUY_ONLY)
        setup = start_setup(bar(0, open_=100, high=100.5, low=98, close=100), level, Direction.BUY, 0, .25, .40)
        self.assertEqual(advance_setup(setup, bar(1, close=99.5)), ("active", False))
        self.assertEqual(advance_setup(setup, bar(2, close=99.25)), ("invalidated", False))


if __name__ == "__main__":
    unittest.main()

