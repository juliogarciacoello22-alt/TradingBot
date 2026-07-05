import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_shadow_vs_real_post_pr19 import collect_metrics, format_markdown


def _write_jsonl(path: Path, rows):
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


class ShadowVsRealPostPR19AuditTests(unittest.TestCase):
    def test_collect_metrics_keeps_shadow_and_real_contracts_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            _write_jsonl(
                session_dir / "signal_engine_full_path_snapshots.jsonl",
                [
                    {
                        "snapshot": {
                            "stage_outputs": {
                                "signal_engine": {
                                    "last_valid_entry_reason": "mitigation_light_true",
                                    "last_build_signal_reason": "valid_entry_failed",
                                    "last_valid_entry_shadow": {
                                        "valid_entry_ab_shadow_would_unlock": True,
                                    },
                                    "signal_is_none": True,
                                }
                            }
                        }
                    },
                    {
                        "snapshot": {
                            "stage_outputs": {
                                "signal_engine": {
                                    "last_valid_entry_reason": "entry_filters_passed",
                                    "last_build_signal_reason": "scalper_generated",
                                    "last_valid_entry_shadow": {
                                        "valid_entry_ab_delta": None,
                                    },
                                    "signal_is_none": False,
                                }
                            }
                        }
                    },
                ],
            )
            _write_jsonl(session_dir / "pipeline_decisions.jsonl", [])
            _write_jsonl(session_dir / "signal_candidates.jsonl", [])
            _write_jsonl(session_dir / "signals_enriched.jsonl", [{"side": "SELL"}])
            _write_jsonl(
                session_dir / "dispatch_events.jsonl",
                [{"allowed": False, "reason": "historical_mode"}],
            )
            _write_jsonl(session_dir / "telegram_events.jsonl", [])

            report = collect_metrics(session_dir)

        metrics = report["metrics"]
        self.assertEqual(metrics["total_snapshots"], 2)
        self.assertEqual(metrics["total_build_signal_results"], 2)
        self.assertEqual(metrics["total_valid_entry_blocks"], 1)
        self.assertEqual(metrics["mitigation_light_true"], 1)
        self.assertEqual(metrics["v2_shadow_would_unlock"], 1)
        self.assertEqual(metrics["shadow_generated_signals"], 1)
        self.assertEqual(metrics["real_generated_signals"], 1)
        self.assertEqual(metrics["dispatch_blocked"], 1)
        self.assertEqual(metrics["shadow_signal_real_block_cases"], 1)
        self.assertEqual(metrics["real_signal_not_dispatched_cases"], 1)

    def test_format_markdown_includes_interpretation_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp)
            for filename in (
                "signal_engine_full_path_snapshots.jsonl",
                "pipeline_decisions.jsonl",
                "signal_candidates.jsonl",
                "signals_enriched.jsonl",
                "dispatch_events.jsonl",
                "telegram_events.jsonl",
            ):
                _write_jsonl(session_dir / filename, [])

            markdown = format_markdown(collect_metrics(session_dir))

        self.assertIn("SHADOW vs REAL Post-PR19 Audit Metrics", markdown)
        self.assertIn("not trade authorization", markdown)


if __name__ == "__main__":
    unittest.main()
