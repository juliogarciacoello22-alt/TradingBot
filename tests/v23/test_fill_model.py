import unittest

from backtesting.v23.fill_model import FillModel, Position
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
    def position(self, model, side=Direction.BUY):
        attempt = model.open_next_bar(
            signal(side),
            bar(1, open_=100.0, high=102.0, low=98.0, close=100.0),
            1,
        )
        self.assertIsNotNone(attempt.position)
        return attempt.position

    def test_entry_cannot_fill_on_signal_bar(self):
        model = FillModel(StrategyConfigV23())
        attempt = model.open_next_bar(signal(), bar(0), 0)
        self.assertIsNone(attempt.position)
        self.assertEqual(attempt.rejection_reason, "entry_not_after_signal")

    def test_entry_fills_at_next_bar_open_with_adverse_slippage(self):
        model = FillModel(StrategyConfigV23(entry_slippage_ticks=1))
        attempt = model.open_next_bar(
            signal(),
            bar(1, open_=100.5, high=102.0, low=100.0, close=101.0),
            1,
        )
        self.assertEqual(attempt.position.signal.entry, 100.75)
        self.assertEqual(attempt.position.entry_timestamp, bar(1).timestamp)
        self.assertEqual(attempt.position.signal.risk_points, 1.75)

    def test_entry_slippage_is_capped_at_reachable_bar_extreme(self):
        model = FillModel(StrategyConfigV23(entry_slippage_ticks=1))
        buy = model.open_next_bar(
            signal(),
            bar(1, open_=100.0, high=100.0, low=99.5, close=100.0),
            1,
        )
        sell = model.open_next_bar(
            signal(Direction.SELL),
            bar(1, open_=100.0, high=100.5, low=100.0, close=100.0),
            1,
        )
        self.assertEqual(buy.position.signal.entry, 100.0)
        self.assertEqual(sell.position.signal.entry, 100.0)

    def test_gap_crossing_stop_cancels_pending_entry(self):
        model = FillModel(StrategyConfigV23())
        attempt = model.open_next_bar(
            signal(),
            bar(1, open_=98.0, high=99.0, low=97.0, close=98.5),
            1,
        )
        self.assertIsNone(attempt.position)
        self.assertEqual(attempt.rejection_reason, "entry_gap_crossed_stop")

    def test_stop_wins_intrabar_conflict(self):
        model = FillModel(StrategyConfigV23(entry_slippage_ticks=0))
        position = self.position(model)
        result = model.resolve(position, bar(1, open_=100, high=102, low=98), 1)
        self.assertEqual(result.outcome, "STOP")
        self.assertEqual(result.net_r, -1.0)

    def test_buy_stop_gap_uses_adverse_open(self):
        model = FillModel(StrategyConfigV23(entry_slippage_ticks=0, exit_slippage_ticks=1))
        position = Position(signal(), 0, bar(0).timestamp)
        result = model.resolve(
            position,
            bar(1, open_=90.0, high=91.0, low=89.0, close=90.0),
            1,
        )
        self.assertEqual(result.outcome, "STOP")
        self.assertEqual(result.exit_price, 89.75)
        self.assertAlmostEqual(result.net_r, -10.25)

    def test_stop_slippage_never_leaves_observed_range(self):
        model = FillModel(StrategyConfigV23(entry_slippage_ticks=0, exit_slippage_ticks=1))
        buy = model.resolve(
            Position(signal(), 0, bar(0).timestamp),
            bar(1, open_=90.0, high=91.0, low=90.0, close=90.0),
            1,
        )
        sell = model.resolve(
            Position(signal(Direction.SELL), 0, bar(0).timestamp),
            bar(1, open_=110.0, high=110.0, low=109.0, close=110.0),
            1,
        )
        self.assertEqual(buy.exit_price, 90.0)
        self.assertEqual(sell.exit_price, 110.0)

    def test_sell_stop_gap_uses_adverse_open(self):
        model = FillModel(StrategyConfigV23(entry_slippage_ticks=0, exit_slippage_ticks=1))
        position = Position(signal(Direction.SELL), 0, bar(0).timestamp)
        result = model.resolve(
            position,
            bar(1, open_=110.0, high=111.0, low=109.0, close=110.0),
            1,
        )
        self.assertEqual(result.outcome, "STOP")
        self.assertEqual(result.exit_price, 110.25)
        self.assertAlmostEqual(result.net_r, -10.25)

    def test_commission_and_exit_slippage_reduce_result(self):
        config = StrategyConfigV23(entry_slippage_ticks=0, exit_slippage_ticks=1, commission_round_trip=5.0, point_value=20.0)
        model = FillModel(config)
        position = Position(signal(), 0, bar(0).timestamp)
        result = model.resolve(position, bar(1, open_=100, high=102, low=100), 1)
        self.assertEqual(result.outcome, "TP1")
        self.assertAlmostEqual(result.exit_slippage_r, 0.25)
        self.assertAlmostEqual(result.commission_r, 0.25)
        self.assertAlmostEqual(result.net_r, 1.0)


if __name__ == "__main__":
    unittest.main()
