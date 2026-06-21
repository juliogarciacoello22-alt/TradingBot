import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backtesting.v23.data_loader import LoadedDataset, load_last_file
from backtesting.v23.runner import BacktestRunnerV23, RunMetadata, sort_rejections
from core.strategy_v23.config import StrategyConfigV23
from core.strategy_v23.models import Direction, SignalDecision

from .helpers import bar


class LoaderAndDeterminismTests(unittest.TestCase):
    metadata = RunMetadata("0" * 40, datetime(2026, 6, 21, tzinfo=timezone.utc))

    def test_loader_validates_ninjatrader_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.Last.txt"
            path.write_text(
                "20251104 080000;100;101;99;100.5;10\n"
                "20251104 080100;100.5;102;100;101.5;20\n",
                encoding="utf-8",
            )
            dataset = load_last_file(path, timezone_name="America/Chicago", tick_size=.25)
            self.assertEqual(len(dataset.bars), 2)
            self.assertEqual(len(dataset.sha256), 64)

    def test_runner_is_deterministic(self):
        bars = tuple(
            bar(index, open_=100 + index * .25, high=101 + index * .25,
                low=99 + index * .25, close=100.5 + index * .25, volume=100 + index)
            for index in range(80)
        )
        dataset = LoadedDataset(Path("synthetic"), "ABC", bars)
        first = BacktestRunnerV23(StrategyConfigV23()).run(dataset, metadata=self.metadata)
        second = BacktestRunnerV23(StrategyConfigV23()).run(dataset, metadata=self.metadata)
        self.assertEqual(first.summary, second.summary)
        self.assertEqual(first.signals, second.signals)
        self.assertEqual(first.rejections, second.rejections)
        self.assertEqual(first.manifest["config_sha256"], second.manifest["config_sha256"])

    def test_runner_fills_signal_on_following_bar(self):
        bars = (
            bar(0, open_=100.0, high=101.0, low=99.5, close=100.0),
            bar(1, open_=100.0, high=101.0, low=99.5, close=100.5),
        )
        decision = SignalDecision(
            timestamp=bars[0].timestamp,
            side=Direction.BUY,
            level_id="level",
            level_kind="prior_low",
            event_type="sweep",
            entry=100.0,
            stop=99.0,
            risk_points=1.0,
            tp1=101.5,
            atr14=2.0,
            volume=100.0,
            volume20=90.0,
            confirmations=("volume", "atr_rising"),
            sequence=1,
        )

        class FakeCore:
            def __init__(self, _config):
                self.rejections = []
                self.calls = 0

            def process_bar(self, _bar, *, position_open=False):
                self.calls += 1
                return decision if self.calls == 1 else None

        dataset = LoadedDataset(Path("synthetic"), "ABC", bars)
        with patch("backtesting.v23.runner.StrategyCoreV23", FakeCore):
            result = BacktestRunnerV23(StrategyConfigV23()).run(dataset, metadata=self.metadata)

        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].signal_timestamp, bars[0].timestamp)
        self.assertEqual(result.trades[0].entry_timestamp, bars[1].timestamp)
        self.assertGreater(result.trades[0].entry_timestamp, result.trades[0].signal_timestamp)
        self.assertEqual(result.trades[0].entry, 100.25)
        self.assertEqual(result.trades[0].stop, 99.0)
        self.assertEqual(result.trades[0].risk_points, 1.25)
        self.assertEqual(result.trades[0].tp1, 102.25)
        self.assertEqual(result.manifest["commit_hash"], "0" * 40)
        self.assertEqual(result.manifest["execution_timestamp"], "2026-06-21T00:00:00+00:00")

    def test_rejections_are_sorted_chronologically(self):
        from core.strategy_v23.models import Rejection

        later = Rejection(bar(2).timestamp, "core")
        earlier = Rejection(bar(1).timestamp, "execution")
        self.assertEqual(sort_rejections([later, earlier]), [earlier, later])


if __name__ == "__main__":
    unittest.main()
