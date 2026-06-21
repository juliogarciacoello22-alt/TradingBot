import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from backtesting.v23.data_loader import LoadedDataset, load_last_file
from backtesting.v23.runner import BacktestRunnerV23
from core.strategy_v23.config import StrategyConfigV23

from .helpers import bar


class LoaderAndDeterminismTests(unittest.TestCase):
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
        first = BacktestRunnerV23(StrategyConfigV23()).run(dataset)
        second = BacktestRunnerV23(StrategyConfigV23()).run(dataset)
        self.assertEqual(first.summary, second.summary)
        self.assertEqual(first.signals, second.signals)
        self.assertEqual(first.rejections, second.rejections)
        self.assertEqual(first.manifest["config_sha256"], second.manifest["config_sha256"])


if __name__ == "__main__":
    unittest.main()

