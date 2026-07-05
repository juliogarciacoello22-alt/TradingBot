import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.import_historical_playback_readonly import import_historical_playback, load_bars


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class HistoricalPlaybackImportReadonlyTests(unittest.TestCase):
    def test_imports_csv_as_feed_only_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bars.csv"
            source.write_text(
                "\n".join(
                    [
                        "timestamp,open,high,low,close,volume",
                        "2026-01-02T09:30:00-06:00,100,101,99,100.5,10",
                        "2026-01-02T09:31:00-06:00,100.5,102,100,101.5,12",
                    ]
                ),
                encoding="utf-8",
            )

            session_dir = import_historical_playback(
                source,
                logs_root=root / "sessions",
                session_id="unit_historical_import",
            )

            feed = _read_jsonl(session_dir / "feed_events.jsonl")
            metadata = json.loads((session_dir / "session_metadata.json").read_text(encoding="utf-8"))
            decisions = (session_dir / "pipeline_decisions.jsonl").read_text(encoding="utf-8")
            snapshots = (session_dir / "signal_engine_full_path_snapshots.jsonl").read_text(encoding="utf-8")

        self.assertEqual(len(feed), 2)
        self.assertTrue(all(row["pipeline_executed"] is False for row in feed))
        self.assertTrue(all(row["no_dispatch"] is True for row in feed))
        self.assertEqual(metadata["source_type"], "historical_playback")
        self.assertFalse(metadata["synthetic_fixture_based"])
        self.assertTrue(metadata["no_dispatch"])
        self.assertTrue(metadata["no_live"])
        self.assertFalse(metadata["pipeline_processed"])
        self.assertFalse(metadata["send_signal_called"])
        self.assertEqual(metadata["orders_sent"], 0)
        self.assertEqual(decisions, "")
        self.assertEqual(snapshots, "")

    def test_fixture_flag_marks_synthetic_without_claiming_real_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bars.jsonl"
            source.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-01-02T09:30:00-06:00",
                        "open": 100,
                        "high": 101,
                        "low": 99,
                        "close": 100,
                        "volume": 1,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            session_dir = import_historical_playback(
                source,
                logs_root=root / "sessions",
                session_id="unit_fixture_import",
                synthetic_fixture_based=True,
            )
            metadata = json.loads((session_dir / "session_metadata.json").read_text(encoding="utf-8"))

        self.assertTrue(metadata["synthetic_fixture_based"])
        self.assertEqual(metadata["source_type"], "historical_playback")

    def test_loads_ninjatrader_last_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "bars.Last.txt"
            source.write_text("20260102 093000;100;101;99;100.5;10\n", encoding="utf-8")

            bars = load_bars(source, "txt")

        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].timestamp, "20260102 093000")

    def test_does_not_require_env_or_server_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bars.csv"
            source.write_text(
                "timestamp,open,high,low,close,volume\n2026-01-02T09:30:00-06:00,1,2,1,2,1\n",
                encoding="utf-8",
            )

            with patch("os.getenv", side_effect=AssertionError("os.getenv should not be used")):
                session_dir = import_historical_playback(
                    source,
                    logs_root=root / "sessions",
                    session_id="unit_no_env",
                )

                self.assertTrue((session_dir / "feed_events.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
