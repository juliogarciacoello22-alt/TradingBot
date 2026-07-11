import unittest

from core.audit_session_logger import (
    _format_summary_md,
    _structured_reason_counts,
    _top_reason_counts,
)


class SessionSummaryStructuredReasonsTests(unittest.TestCase):
    def test_structured_reason_counts_aggregate_pipeline_decisions(self):
        records = [
            {
                "terminal_stage": "build_signal",
                "terminal_reason": "valid_entry_failed",
                "terminal_subreason": "missing_displacement",
                "build_signal_reason": "valid_entry_failed",
                "valid_entry_reason": "missing_displacement",
                "ob_reason": "raw_ob_missing",
                "timing_reason": "ok",
            },
            {
                "terminal_stage": "build_signal",
                "terminal_reason": "valid_entry_failed",
                "terminal_subreason": "mitigation_light_true",
                "build_signal_reason": "valid_entry_failed",
                "valid_entry_reason": "mitigation_light_true",
                "ob_reason": "ok",
                "timing_reason": "low volatility",
            },
            {
                "terminal_stage": "final_signal",
                "terminal_reason": "ok",
                "build_signal_reason": "scalper_generated",
                "valid_entry_reason": "entry_filters_passed",
                "ob_reason": "ok",
                "timing_reason": "ok",
            },
        ]

        counts = _structured_reason_counts(records)
        self.assertEqual(counts["terminal_reason"], {"valid_entry_failed": 2, "ok": 1})
        self.assertEqual(
            counts["terminal_subreason"],
            {"missing_displacement": 1, "mitigation_light_true": 1},
        )
        self.assertEqual(counts["ob_reason"], {"ok": 2, "raw_ob_missing": 1})
        self.assertEqual(counts["timing_reason"], {"ok": 2, "low volatility": 1})

    def test_missing_fields_are_not_counted(self):
        counts = _structured_reason_counts([
            {"terminal_reason": None},
            {"reason": "no_final_signal"},
            {},
        ])
        self.assertEqual(counts["terminal_reason"], {})
        self.assertEqual(counts["terminal_subreason"], {})
        self.assertEqual(counts["ob_reason"], {})

    def test_top_reason_counts_are_deterministic(self):
        structured_counts = {
            "terminal_reason": {
                "ok": 1,
                "valid_entry_failed": 4,
                "timing_invalid": 2,
            }
        }
        self.assertEqual(
            _top_reason_counts(structured_counts, "terminal_reason", limit=2),
            [["valid_entry_failed", 4], ["timing_invalid", 2]],
        )

    def test_markdown_contains_structured_sections(self):
        summary = {
            "structured_reason_counts": {
                "terminal_reason": {"valid_entry_failed": 3},
                "terminal_subreason": {"missing_displacement": 2},
                "ob_reason": {"raw_ob_missing": 2},
                "timing_reason": {"ok": 3},
            }
        }
        markdown = _format_summary_md(summary)
        self.assertIn("## Structured terminal reasons", markdown)
        self.assertIn("- valid_entry_failed: 3", markdown)
        self.assertIn("## Structured terminal subreasons", markdown)
        self.assertIn("- missing_displacement: 2", markdown)
        self.assertIn("## Structured OB reasons", markdown)
        self.assertIn("- raw_ob_missing: 2", markdown)
        self.assertIn("## Structured timing reasons", markdown)
        self.assertIn("- ok: 3", markdown)


if __name__ == "__main__":
    unittest.main()
