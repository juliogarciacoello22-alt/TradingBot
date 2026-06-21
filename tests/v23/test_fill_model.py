import unittest

from backtesting.v23.fill_model import FillModel
from core.strategy_v23.config import StrategyConfigV23
from core.strategy_v23.models import Direction, SignalDecision

from .helpers import bar


def signal(side=Direction.BUY):
    return SignalDecision(
        timestamp=bar(0).timestamp,
        side=side,
        level_id="level",
        level_kind="prior_low" if side == Direction.BUY else "prior_high",
        event_type="sweep",
        entry=100.0,
        stop=99.0 if side == Direction.BUY else 101.0,
        risk_points=1.0,
        tp1=101.5 if side == Direction.BUY else 98.5,
        atr14=2.0,
        volume=100,
        volume20=90,
        confirmations=("volume", "atr_rising"),
        sequence=1,
    )


class FillModelTests(unittest.TestCase):
    def test_position_cannot_exit_on_entry_bar(self):
        model = FillModel(StrategyConfigV23())
        position = model.open(signal(), 5)
        self.assertIsNone(model.resolve(position, bar(0, high=102, low=98), 5))

    def test_stop_wins_intrabar_conflict(self):
        model = FillModel(StrategyConfigV23())
        position = model.open(signal(), 0)
        result = model.resolve(position, bar(1, high=102, low=98), 1)
        self.assertEqual(result.outcome, "STOP")
        self.assertEqual(result.net_r, -1.0)

    def test_commission_and_exit_slippage_reduce_result(self):
        config = StrategyConfigV23(exit_slippage_ticks=1, commission_round_trip=5.0, point_value=20.0)
        result = FillModel(config).resolve(FillModel(config).open(signal(), 0), bar(1, high=102, low=100), 1)
        self.assertEqual(result.outcome, "TP1")
        self.assertAlmostEqual(result.exit_slippage_r, 0.25)
        self.assertAlmostEqual(result.commission_r, 0.25)
        self.assertAlmostEqual(result.net_r, 1.0)


if __name__ == "__main__":
    unittest.main()

