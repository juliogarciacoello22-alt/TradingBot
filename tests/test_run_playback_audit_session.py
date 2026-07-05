import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.audit_shadow_vs_real_post_pr19 import collect_metrics
from tools.run_playback_audit_session import create_playback_audit_session


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class PlaybackAuditSessionRunnerTests(unittest.TestCase):
    def test_generates_required_non_empty_audit_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = create_playback_audit_session(
                logs_root=Path(tmp),
                session_id="unit_playback_audit",
            )

            feed = _read_jsonl(session_dir / "feed_events.jsonl")
            decisions = _read_jsonl(session_dir / "pipeline_decisions.jsonl")
            snapshots = _read_jsonl(session_dir / "signal_engine_full_path_snapshots.jsonl")

        self.assertGreater(len(feed), 0)
        self.assertGreater(len(decisions), 0)
        self.assertGreater(len(snapshots), 0)

    def test_session_is_explicitly_non_live_and_no_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = create_playback_audit_session(
                logs_root=Path(tmp),
                session_id="unit_no_dispatch",
            )

            metadata = json.loads((session_dir / "session_metadata.json").read_text(encoding="utf-8"))
            dispatch = _read_jsonl(session_dir / "dispatch_events.jsonl")
            telegram = _read_jsonl(session_dir / "telegram_events.jsonl")

        self.assertFalse(metadata["send_signal_called"])
        self.assertFalse(metadata["websocket_opened"])
        self.assertFalse(metadata["telegram_enabled"])
        self.assertEqual(metadata["orders_sent"], 0)
        self.assertTrue(all(row["allowed"] is False for row in dispatch))
        self.assertTrue(all(row["sent"] is False for row in telegram))

    def test_does_not_require_env_or_import_server(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("os.getenv", side_effect=AssertionError("os.getenv should not be used")):
                session_dir = create_playback_audit_session(
                    logs_root=Path(tmp),
                    session_id="unit_no_env",
                )

                self.assertTrue((session_dir / "session_summary.json").exists())

    def test_generated_session_is_consumed_by_shadow_vs_real_auditor(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = create_playback_audit_session(
                logs_root=Path(tmp),
                session_id="unit_auditor_contract",
            )

            report = collect_metrics(session_dir)

        metrics = report["metrics"]
        self.assertEqual(metrics["total_snapshots"], 2)
        self.assertEqual(metrics["total_build_signal_results"], 2)
        self.assertEqual(metrics["total_valid_entry_blocks"], 1)
        self.assertEqual(metrics["v2_shadow_would_unlock"], 1)
        self.assertEqual(metrics["real_generated_signals"], 1)
        self.assertEqual(metrics["dispatch_blocked"], 1)


if __name__ == "__main__":
    unittest.main()
