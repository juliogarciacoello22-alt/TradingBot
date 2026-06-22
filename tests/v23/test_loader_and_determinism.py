import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backtesting.v23.data_loader import ExpectedClosure, LoadedDataset, load_expected_closures, load_last_file
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

    def test_loader_rejects_unexpected_long_intraday_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gap.Last.txt"
            path.write_text(
                "20251104 080000;100;101;99;100.5;10\n"
                "20251104 120000;100.5;102;100;101.5;20\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Unexpected 239-minute gap"):
                load_last_file(path, timezone_name="America/Chicago", tick_size=.25)

    def test_loader_does_not_hide_missing_day_behind_session_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "false-closure.Last.txt"
            path.write_text(
                "20251104 080000;100;101;99;100.5;10\n"
                "20251104 170000;100.5;102;100;101.5;20\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Unexpected 539-minute gap"):
                load_last_file(path, timezone_name="America/Chicago", tick_size=.25)

    def test_loader_audits_short_gap_and_expected_session_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audited.Last.txt"
            path.write_text(
                "20251104 155900;100;101;99;100.5;10\n"
                "20251104 170000;100.5;102;100;101.5;20\n"
                "20251104 170600;101.5;102;101;101.75;15\n",
                encoding="utf-8",
            )
            dataset = load_last_file(path, timezone_name="America/Chicago", tick_size=.25)

            self.assertEqual(
                [gap.classification for gap in dataset.gaps],
                ["daily_maintenance", "short_provider_gap"],
            )
            self.assertEqual([gap.missing_minutes for gap in dataset.gaps], [60, 5])

    def test_loader_rejects_one_or_two_missing_sessions(self):
        cases = (
            ("20251104 155900", "20251105 170000", 1500),
            ("20251104 155900", "20251106 170000", 2940),
        )
        for previous, current, missing in cases:
            with self.subTest(current=current), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "missing-session.Last.txt"
                path.write_text(
                    f"{previous};100;101;99;100.5;10\n"
                    f"{current};100.5;102;100;101.5;20\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, f"Unexpected {missing}-minute gap"):
                    load_last_file(path, timezone_name="America/Chicago", tick_size=.25)

    def test_loader_accepts_exact_weekend_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "weekend.Last.txt"
            path.write_text(
                "20251107 155900;100;101;99;100.5;10\n"
                "20251109 170000;100.5;102;100;101.5;20\n",
                encoding="utf-8",
            )
            dataset = load_last_file(path, timezone_name="America/Chicago", tick_size=.25)
            self.assertEqual(dataset.gaps[0].classification, "weekend_closure")

    def test_holiday_requires_exact_explicit_calendar_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "holiday.Last.txt"
            calendar = Path(directory) / "closures.json"
            data.write_text(
                "20251126 121500;100;101;99;100.5;10\n"
                "20251127 170000;100.5;102;100;101.5;20\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Unexpected"):
                load_last_file(data, timezone_name="America/Chicago", tick_size=.25)

            calendar.write_text(
                '[{"last_bar":"2025-11-26T12:15:00-06:00",'
                '"next_bar":"2025-11-27T17:00:00-06:00",'
                '"label":"thanksgiving"}]',
                encoding="utf-8",
            )
            closure_calendar = load_expected_closures(calendar, timezone_name="America/Chicago")
            dataset = load_last_file(
                data,
                timezone_name="America/Chicago",
                tick_size=.25,
                closure_calendar=closure_calendar,
            )
            self.assertEqual(dataset.gaps[0].classification, "calendar:thanksgiving")
            self.assertEqual(dataset.closure_calendar_sha256, closure_calendar.sha256)
            self.assertEqual(len(dataset.closure_calendar_sha256), 64)

    def test_early_close_is_not_daily_maintenance_without_calendar(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "early-close.Last.txt"
            path.write_text(
                "20251128 120000;100;101;99;100.5;10\n"
                "20251128 170000;100.5;102;100;101.5;20\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "Unexpected 299-minute gap"):
                load_last_file(path, timezone_name="America/Chicago", tick_size=.25)

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

        class FakeStream:
            def __init__(self, _config):
                self.rejections = []
                self.calls = 0

            def process_closed_bar(self, _bar, *, position_open=False):
                self.calls += 1
                return decision if self.calls == 1 else None

        dataset = LoadedDataset(Path("synthetic"), "ABC", bars)
        with patch("backtesting.v23.runner.StrategyStreamV23", FakeStream):
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

    def test_rejection_identity_preserves_distinct_setups_and_removes_true_duplicates(self):
        from core.strategy_v23.models import Rejection

        first = Rejection(
            bar(1).timestamp,
            "opposite_acceptance",
            "sweep_high",
            Direction.SELL,
            level_id="level-a",
            setup_id="setup-a",
        )
        second = Rejection(
            bar(1).timestamp,
            "opposite_acceptance",
            "sweep_high",
            Direction.SELL,
            level_id="level-b",
            setup_id="setup-b",
        )
        normalized = sort_rejections([first, first, second])

        self.assertEqual(len(normalized), 2)
        self.assertNotEqual(first.event_id, second.event_id)
        self.assertEqual({item.setup_id for item in normalized}, {"setup-a", "setup-b"})


if __name__ == "__main__":
    unittest.main()
