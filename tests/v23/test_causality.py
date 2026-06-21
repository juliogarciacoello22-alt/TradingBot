import unittest

from core.strategy_v23.indicator_engine import BarAggregator, confirmed_pivot

from .helpers import bar


class CausalityTests(unittest.TestCase):
    def test_aggregator_exposes_only_completed_bucket(self):
        aggregator = BarAggregator(5)
        for minute in range(5):
            self.assertFalse(aggregator.update(bar(minute)))
            self.assertEqual(len(aggregator.completed), 0)
        self.assertTrue(aggregator.update(bar(5)))
        self.assertEqual(len(aggregator.completed), 1)

    def test_pivot_requires_two_right_bars(self):
        series = [
            bar(0, high=101),
            bar(5, high=102),
            bar(10, high=110),
            bar(15, high=103),
        ]
        self.assertIsNone(confirmed_pivot(series))
        series.append(bar(20, high=104))
        pivot, is_high, is_low = confirmed_pivot(series)
        self.assertEqual(pivot.high, 110)
        self.assertTrue(is_high)
        self.assertFalse(is_low)


if __name__ == "__main__":
    unittest.main()

