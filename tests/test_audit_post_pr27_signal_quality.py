import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_post_pr27_signal_quality import collect_quality


def _write_jsonl(path: Path, rows: list[dict]):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class PostPR27SignalQualityAuditTests(unittest.TestCase):
    def test_collects_real_outputs_shadow_unlocks_and_confirmed_zero_event_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp)

            _write_jsonl(
                session / "signal_engine_full_path_snapshots.jsonl",
                [
                    {
                        "event": "signal_engine_v4_full_path_snapshot",
                        "snapshot": {
                            "decision_id": "d1",
                            "timestamp": "t1",
                            "price": 100,
                            "stage_outputs": {
                                "signal_engine": {
                                    "last_build_signal_reason": "scalper_generated",
                                    "last_valid_entry_reason": "entry_filters_passed",
                                    "signal_is_none": False,
                                    "last_valid_entry_shadow": {},
                                }
                            },
                            "missing_fields": [],
                        },
                    },
                    {
                        "event": "signal_engine_v4_full_path_snapshot",
                        "snapshot": {
                            "decision_id": "d2",
                            "timestamp": "t2",
                            "price": 101,
                            "stage_outputs": {
                                "signal_engine": {
                                    "last_build_signal_reason": "valid_entry_failed",
                                    "last_valid_entry_reason": "mitigation_light_true",
                                    "signal_is_none": True,
                                    "last_valid_entry_shadow": {
                                        "valid_entry_ab_shadow_would_unlock": True
                                    },
                                }
                            },
                            "missing_fields": ["snapshot.micro.ob"],
                        },
                    },
                ],
            )
            _write_jsonl(
                session / "pipeline_decisions.jsonl",
                [
                    {
                        "event": "pipeline_decision",
                        "stage": "process",
                        "allowed": False,
                        "reason": "no_final_signal",
                    }
                ],
            )
            _write_jsonl(session / "dispatch_events.jsonl", [])
            _write_jsonl(session / "telegram_events.jsonl", [])

            report = collect_quality(session)

        self.assertEqual(report["metrics"]["total_snapshots"], 2)
        self.assertEqual(report["metrics"]["pipeline_decisions"], 1)
        self.assertEqual(report["metrics"]["real_generated_signals"], 1)
        self.assertEqual(report["metrics"]["shadow_unlocks"], 1)
        self.assertEqual(report["metrics"]["dispatch_events"], 0)
        self.assertEqual(report["metrics"]["telegram_events"], 0)
        self.assertEqual(report["artifact_presence"]["dispatch_events.jsonl"], True)
        self.assertEqual(report["artifact_presence"]["telegram_events.jsonl"], True)
        self.assertEqual(report["missing_artifacts"], [])
        self.assertEqual(report["classification"]["safety"], "PASS")
        self.assertEqual(report["classification"]["operational_authorization"], "NO_GO")
        self.assertEqual(report["reason_counts"]["missing_fields"], [("snapshot.micro.ob", 1)])

    def test_missing_dispatch_or_telegram_artifacts_make_safety_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp)
            _write_jsonl(session / "signal_engine_full_path_snapshots.jsonl", [])
            _write_jsonl(session / "pipeline_decisions.jsonl", [])

            report = collect_quality(session)

        self.assertEqual(report["metrics"]["dispatch_events"], 0)
        self.assertEqual(report["metrics"]["telegram_events"], 0)
        self.assertEqual(report["artifact_presence"]["dispatch_events.jsonl"], False)
        self.assertEqual(report["artifact_presence"]["telegram_events.jsonl"], False)
        self.assertEqual(
            report["missing_artifacts"],
            ["dispatch_events.jsonl", "telegram_events.jsonl"],
        )
        self.assertEqual(report["classification"]["safety"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()

