import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.audit_shadow_vs_real_post_pr19 import collect_metrics
from tools.import_historical_playback_readonly import import_historical_playback
from tools.process_historical_playback_audit_only import process_historical_playback_audit_only


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class HistoricalPlaybackAuditOnlyProcessorTests(unittest.TestCase):
    def _create_imported_session(self, root: Path) -> Path:
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
        return import_historical_playback(
            source,
            logs_root=root / "sessions",
            session_id="unit_historical_import",
        )

    def test_processes_imported_feed_into_audit_pipeline_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = self._create_imported_session(root)

            processed_dir = process_historical_playback_audit_only(session_dir)

            feed = _read_jsonl(processed_dir / "feed_events.jsonl")
            decisions = _read_jsonl(processed_dir / "pipeline_decisions.jsonl")
            snapshots = _read_jsonl(processed_dir / "signal_engine_full_path_snapshots.jsonl")
            metadata = json.loads((processed_dir / "session_metadata.json").read_text(encoding="utf-8"))

        self.assertEqual(processed_dir, session_dir)
        self.assertEqual(len(decisions), len(feed))
        self.assertEqual(len(snapshots), len(feed))
        self.assertTrue(metadata["audit_pipeline_processed"])
        self.assertEqual(metadata["pipeline_processing_mode"], "AUDIT_ONLY_FEED_REPLAY")
        self.assertFalse(metadata["signal_engine_called"])
        self.assertFalse(metadata["build_signal_called"])
        self.assertFalse(metadata["send_signal_called"])
        self.assertTrue(metadata["no_dispatch"])
        self.assertTrue(metadata["no_live"])
        self.assertEqual(metadata["orders_sent"], 0)
        self.assertTrue(all(row["final_decision"] == "NO_TRADE" for row in decisions))
        self.assertTrue(all(row["dispatch_attempted"] is False for row in decisions))
        self.assertTrue(
            all(
                row["snapshot"]["stage_outputs"]["signal_engine"]["signal_engine_called"] is False
                for row in snapshots
            )
        )

    def test_preserves_empty_dispatch_and_telegram_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = self._create_imported_session(Path(tmp))

            process_historical_playback_audit_only(session_dir)

            dispatch = (session_dir / "dispatch_events.jsonl").read_text(encoding="utf-8")
            telegram = (session_dir / "telegram_events.jsonl").read_text(encoding="utf-8")

        self.assertEqual(dispatch, "")
        self.assertEqual(telegram, "")

    def test_does_not_require_env_or_server_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = self._create_imported_session(Path(tmp))

            with patch("os.getenv", side_effect=AssertionError("os.getenv should not be used")):
                processed_dir = process_historical_playback_audit_only(session_dir)

            self.assertTrue((processed_dir / "pipeline_decisions.jsonl").exists())

    def test_rejects_non_imported_or_empty_feed_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "sessions" / "bad_session"
            session_dir.mkdir(parents=True)
            (session_dir / "session_metadata.json").write_text(
                json.dumps({"source_type": "historical_playback", "no_dispatch": True, "no_live": True}) + "\n",
                encoding="utf-8",
            )
            (session_dir / "feed_events.jsonl").write_text("", encoding="utf-8")

            with self.assertRaises(ValueError):
                process_historical_playback_audit_only(session_dir)

    def test_processed_session_is_consumed_by_shadow_vs_real_auditor(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = self._create_imported_session(Path(tmp))
            process_historical_playback_audit_only(session_dir)

            report = collect_metrics(session_dir)

        metrics = report["metrics"]
        self.assertEqual(metrics["total_snapshots"], 2)
        self.assertEqual(metrics["pipeline_decisions"], 2)
        self.assertEqual(metrics["dispatch_events"], 0)
        self.assertEqual(metrics["telegram_events"], 0)
        self.assertEqual(metrics["real_generated_signals"], 0)
        self.assertEqual(metrics["v2_shadow_would_unlock"], 0)


if __name__ == "__main__":
    unittest.main()
