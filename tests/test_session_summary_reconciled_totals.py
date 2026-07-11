import json
import tempfile
import unittest
from pathlib import Path

from core.audit_session_logger import _build_summary, _format_summary_md


class SessionSummaryReconciledTotalsTests(unittest.TestCase):
    def _session_dir(self, root: str) -> Path:
        session_dir = Path(root)
        for name in (
            "feed_events.jsonl",
            "pipeline_decisions.jsonl",
            "signal_candidates.jsonl",
            "signals_enriched.jsonl",
            "dispatch_events.jsonl",
            "telegram_events.jsonl",
            "missed_trade_candidates.jsonl",
            "signal_engine_full_path_snapshots.jsonl",
        ):
            (session_dir / name).write_text("", encoding="utf-8")
        (session_dir / "server_console.log").write_text("", encoding="utf-8")
        return session_dir

    def test_pipeline_total_uses_structured_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = self._session_dir(tmp)
            records = [
                {"event": "pipeline_decision", "terminal_stage": "build_signal"},
                {"event": "pipeline_decision", "terminal_stage": "build_signal"},
                {"event": "pipeline_decision", "terminal_stage": "final_signal", "terminal_reason": "ok"},
            ]
            (session_dir / "pipeline_decisions.jsonl").write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            summary = _build_summary(session_dir)

        self.assertEqual(summary["total_pipeline_executed"], 3)
        self.assertEqual(summary["total_velas_recibidas"], 0)

    def test_build_final_and_execution_counts_are_reconciled(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = self._session_dir(tmp)
            records = [
                {
                    "event": "pipeline_decision",
                    "terminal_stage": "final_signal",
                    "terminal_reason": "ok",
                    "build_signal_reason": "scalper_generated",
                },
                {
                    "event": "pipeline_decision",
                    "terminal_stage": "final_signal",
                    "terminal_reason": "ok",
                    "build_signal_reason": "swing_generated",
                },
                {
                    "event": "pipeline_decision",
                    "terminal_stage": "execution_engine",
                    "terminal_reason": "execution_rejected",
                    "build_signal_reason": "scalper_generated",
                },
                {
                    "event": "pipeline_decision",
                    "terminal_stage": "build_signal",
                    "terminal_reason": "valid_entry_failed",
                    "build_signal_reason": "valid_entry_failed",
                },
            ]
            (session_dir / "pipeline_decisions.jsonl").write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            summary = _build_summary(session_dir)

        self.assertEqual(summary["total_build_signal_generated"], 3)
        self.assertEqual(summary["total_final_signals"], 2)
        self.assertEqual(summary["total_execution_rejected"], 1)
        self.assertEqual(summary["total_senales_despachadas"], 0)

    def test_feed_pipeline_count_is_preserved_when_higher(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = self._session_dir(tmp)
            feed_records = [
                {"pipeline_executed": True},
                {"pipeline_executed": True},
                {"pipeline_executed": True},
            ]
            (session_dir / "feed_events.jsonl").write_text(
                "".join(json.dumps(record) + "\n" for record in feed_records),
                encoding="utf-8",
            )
            (session_dir / "pipeline_decisions.jsonl").write_text(
                json.dumps({"event": "pipeline_decision"}) + "\n",
                encoding="utf-8",
            )
            summary = _build_summary(session_dir)

        self.assertEqual(summary["total_pipeline_executed"], 3)

    def test_markdown_includes_reconciled_totals(self):
        markdown = _format_summary_md(
            {
                "total_pipeline_executed": 72,
                "total_build_signal_generated": 3,
                "total_final_signals": 2,
                "total_execution_rejected": 1,
            }
        )

        self.assertIn("- **Pipeline executed:** 72", markdown)
        self.assertIn("- **Build signals generated:** 3", markdown)
        self.assertIn("- **Final signals:** 2", markdown)
        self.assertIn("- **Execution rejected:** 1", markdown)


if __name__ == "__main__":
    unittest.main()
