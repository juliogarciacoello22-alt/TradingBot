import json
import tempfile
import unittest
from pathlib import Path

from core.audit_session_logger import write_session_summary
from core.audit_session_logger_patch import enrich_summary_with_v2


class SummaryV2StructuredReconciliationTests(unittest.TestCase):
    def _write_jsonl(self, path: Path, records: list[dict]) -> None:
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    def _empty_session_files(self, session_dir: Path) -> None:
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

    def test_summary_v2_reconciles_generated_build_signals_from_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            self._empty_session_files(session_dir)
            self._write_jsonl(
                session_dir / "pipeline_decisions.jsonl",
                [
                    {"build_signal_reason": "scalper_generated"},
                    {"build_signal_reason": "scalper_generated"},
                    {"build_signal_reason": "swing_generated"},
                    {"build_signal_reason": "valid_entry_failed"},
                ],
            )
            summary = enrich_summary_with_v2(
                {
                    "total_pipeline_executed": 4,
                    "total_build_signal_generated": 3,
                    "total_senales_generadas": 0,
                },
                session_dir,
            )
        self.assertEqual(summary["summary_v2"]["observed_activity"]["build_signal_results"], 3)

    def test_reconciliation_does_not_alias_signal_engine_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            self._empty_session_files(session_dir)
            self._write_jsonl(
                session_dir / "pipeline_decisions.jsonl",
                [
                    {"build_signal_reason": "scalper_generated"},
                    {"build_signal_reason": "swing_generated"},
                ],
            )
            summary = enrich_summary_with_v2(
                {
                    "total_pipeline_executed": 2,
                    "total_build_signal_generated": 2,
                    "total_senales_generadas": 0,
                },
                session_dir,
            )
        observed = summary["summary_v2"]["observed_activity"]
        self.assertEqual(observed["build_signal_results"], 2)
        self.assertEqual(observed["signal_engine_generated"], 0)

    def test_reconciliation_records_structured_source_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            self._empty_session_files(session_dir)
            self._write_jsonl(
                session_dir / "pipeline_decisions.jsonl",
                [{"build_signal_reason": "scalper_generated"}],
            )
            summary = enrich_summary_with_v2(
                {
                    "total_pipeline_executed": 1,
                    "total_build_signal_generated": 1,
                    "total_senales_generadas": 0,
                },
                session_dir,
            )
        self.assertIn(
            "summary_v2_build_signal_zero_but_pipeline_decisions_show_generated",
            summary["summary_v2"]["consistency_warnings"],
        )

    def test_written_json_uses_windows_safe_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            self._empty_session_files(session_dir)
            write_session_summary(str(session_dir))
            output_path = session_dir / "session_summary.json"
            self.assertTrue(output_path.read_bytes().startswith(b"\xef\xbb\xbf"))
            payload = json.loads(output_path.read_text(encoding="utf-8-sig"))
        self.assertIn("Resumen regenerado desde archivos de sesión.", payload["notes"])


if __name__ == "__main__":
    unittest.main()
