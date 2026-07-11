import json
import tempfile
import unittest
from pathlib import Path

from tools.analyze_strategy_behavior import (
    analyze_records,
    build_report,
    discover_sessions,
    format_markdown,
    write_report,
)


class AnalyzeStrategyBehaviorTests(unittest.TestCase):
    def test_analyze_records_builds_consistent_funnel_and_counts(self):
        records = [
            {
                "terminal_stage": "build_signal",
                "terminal_reason": "valid_entry_failed",
                "terminal_subreason": "missing_displacement",
                "build_signal_reason": "valid_entry_failed",
                "ob_reason": "raw_ob_missing",
                "timing_reason": "ok",
            },
            {
                "terminal_stage": "final_signal",
                "terminal_reason": "ok",
                "build_signal_reason": "scalper_generated",
                "ob_reason": "ok",
                "timing_reason": "ok",
            },
            {
                "terminal_stage": "execution_engine",
                "terminal_reason": "execution_rejected",
                "terminal_subreason": "vela previa alcista fuerte",
                "build_signal_reason": "scalper_generated",
                "ob_reason": "ok",
                "timing_reason": "ok",
            },
        ]

        result = analyze_records(records)

        self.assertEqual(result["pipeline_decisions"], 3)
        self.assertEqual(result["funnel"]["build_signal_generated"], 2)
        self.assertEqual(result["funnel"]["final_signals"], 1)
        self.assertEqual(result["funnel"]["execution_rejected"], 1)
        self.assertEqual(result["funnel"]["build_signal_to_final_pct"], 50.0)
        self.assertEqual(result["reason_counts"]["terminal_reason"]["ok"], 1)

    def test_build_report_compares_multiple_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, reasons in (
                ("s1", ["valid_entry_failed", "ok"]),
                ("s2", ["execution_rejected"]),
            ):
                session = root / name
                session.mkdir()
                records = []
                for reason in reasons:
                    records.append(
                        {
                            "terminal_stage": (
                                "final_signal" if reason == "ok" else "execution_engine"
                                if reason == "execution_rejected"
                                else "build_signal"
                            ),
                            "terminal_reason": reason,
                            "build_signal_reason": (
                                "scalper_generated"
                                if reason in {"ok", "execution_rejected"}
                                else "valid_entry_failed"
                            ),
                        }
                    )
                (session / "pipeline_decisions.jsonl").write_text(
                    "".join(json.dumps(record) + "\n" for record in records),
                    encoding="utf-8",
                )

            report = build_report(discover_sessions(root))

        self.assertEqual(report["sessions_analyzed"], 2)
        self.assertEqual(report["aggregate"]["pipeline_decisions"], 3)
        self.assertEqual(report["aggregate"]["funnel"]["build_signal_generated"], 2)
        self.assertEqual(len(report["sessions"]), 2)

    def test_dominant_filter_requires_minimum_count_and_share(self):
        records = [
            {
                "terminal_reason": "valid_entry_failed",
                "terminal_subreason": "missing_displacement",
            }
            for _ in range(20)
        ] + [{"terminal_reason": "ok"} for _ in range(20)]

        result = analyze_records(records)

        self.assertEqual(
            result["dominant_filters"],
            [
                {
                    "reason": "missing_displacement",
                    "count": 20,
                    "share_of_pipeline_pct": 50.0,
                }
            ],
        )

    def test_write_report_creates_json_and_markdown(self):
        report = build_report([])
        with tempfile.TemporaryDirectory() as tmp:
            json_path, md_path = write_report(report, Path(tmp))
            payload = json.loads(json_path.read_text(encoding="utf-8-sig"))
            markdown = md_path.read_text(encoding="utf-8-sig")

        self.assertEqual(payload["report_version"], 1)
        self.assertIn("# BIUMOLO Offline Strategy Behavior Report", markdown)
        self.assertIn("no_sessions_discovered", markdown)

    def test_markdown_contains_session_comparison(self):
        report = {
            "sessions_analyzed": 1,
            "aggregate": analyze_records([]),
            "sessions": [
                {
                    "session_id": "example",
                    "pipeline_decisions": 2,
                    "funnel": {
                        "build_signal_generated": 1,
                        "final_signals": 1,
                        "execution_rejected": 0,
                    },
                }
            ],
            "warnings": [],
        }

        markdown = format_markdown(report)

        self.assertIn("| example | 2 | 1 | 1 | 0 |", markdown)


if __name__ == "__main__":
    unittest.main()
