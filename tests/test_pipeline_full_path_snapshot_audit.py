
import json
import os
import tempfile
import unittest

from core import audit_session_logger
from core.pipeline_live_pro import _emit_full_path_snapshot_audit


class _Candle:
    def __init__(self):
        self.timestamp = 1234567890
        self.close = 101.25


class _SignalEngine:
    last_valid_entry_reason = "entry_filters_passed"
    last_build_signal_reason = "scalper_generated"
    last_valid_entry_shadow = {"valid_entry_ab_delta": "shadow_would_unlock"}


class PipelineFullPathSnapshotAuditTests(unittest.TestCase):
    def test_emit_full_path_snapshot_audit_writes_jsonl_without_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["BIUMOLO_SESSION_DIR"] = tmp
            audit_session_logger.start_session({"test": "pipeline_full_path_snapshot"})
            _emit_full_path_snapshot_audit(
                raw={"timestamp": 1234567890},
                candle=_Candle(),
                tf={"1m": [_Candle()]},
                micro_for_valid_entry={"mitigation_light_reason": "no_close_overlap", "ob": {}},
                timing={"enabled": True},
                delta=10.0,
                context={"bias": "bullish"},
                forecast={"target": 1},
                signal_engine=_SignalEngine(),
                signal={"side": "BUY"},
            )
            path = os.path.join(tmp, "signal_engine_full_path_snapshots.jsonl")
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
            self.assertEqual(len(rows), 1)
            snapshot = rows[0]["snapshot"]
            self.assertEqual(snapshot["stage_outputs"]["signal_engine"]["last_valid_entry_reason"], "entry_filters_passed")
            self.assertEqual(snapshot["missing_fields"], [])

            os.environ.pop("BIUMOLO_SESSION_DIR", None)


if __name__ == "__main__":
    unittest.main()
