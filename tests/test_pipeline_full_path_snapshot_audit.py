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
    def setUp(self):
        self._old_env = os.environ.get("BIUMOLO_SESSION_DIR")
        self._old_dir = getattr(audit_session_logger, "_SESSION_DIR", None)
        self._old_id = getattr(audit_session_logger, "_SESSION_ID", None)
        self._old_meta = dict(getattr(audit_session_logger, "_SESSION_META", {}))
        self._old_registered = getattr(audit_session_logger, "_SUMMARY_REGISTERED", False)

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("BIUMOLO_SESSION_DIR", None)
        else:
            os.environ["BIUMOLO_SESSION_DIR"] = self._old_env
        audit_session_logger._SESSION_DIR = self._old_dir
        audit_session_logger._SESSION_ID = self._old_id
        audit_session_logger._SESSION_META = self._old_meta
        audit_session_logger._SUMMARY_REGISTERED = self._old_registered

    def test_emit_full_path_snapshot_audit_writes_jsonl_without_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["BIUMOLO_SESSION_DIR"] = tmp
            audit_session_logger._SESSION_DIR = None
            audit_session_logger._SESSION_ID = None
            audit_session_logger._SESSION_META = {}
            audit_session_logger._SUMMARY_REGISTERED = False
            audit_session_logger.start_session({"test": "pipeline_full_path_snapshot"})

            _emit_full_path_snapshot_audit(
                raw={"timestamp": 1234567890},
                candle=_Candle(),
                tf={"1m": [_Candle()]},
                micro_for_valid_entry={"mitigation_light_reason": "no_overlap"},
                timing={"session": "ny"},
                delta=12.5,
                context={"bias": "bullish"},
                forecast={"liquidity": "near"},
                signal_engine=_SignalEngine(),
                signal=None,
            )

            path = os.path.join(tmp, "signal_engine_full_path_snapshots.jsonl")
            self.assertTrue(os.path.exists(path))
            with open(path, "r", encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh if line.strip()]

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["event"], "signal_engine_v4_full_path_snapshot")
        self.assertEqual(row["snapshot"]["stage_outputs"]["signal_engine"]["last_valid_entry_reason"], "entry_filters_passed")


if __name__ == "__main__":
    unittest.main()
