import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import audit_session_logger
from core.pipeline_live_pro import _decision_log


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class PipelineDecisionJsonlLoggingTests(unittest.TestCase):
    def test_decision_log_persists_pipeline_decision_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_dir = Path(tmp) / "unit_session"

            with patch.dict("os.environ", {"BIUMOLO_SESSION_DIR": str(session_dir)}):
                audit_session_logger._SESSION_DIR = None
                audit_session_logger._SESSION_ID = None
                audit_session_logger.start_session()

                _decision_log("process", False, "no_final_signal", "side=None mode=None")

                rows = _read_jsonl(session_dir / "pipeline_decisions.jsonl")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event"], "pipeline_decision")
        self.assertEqual(rows[0]["stage"], "process")
        self.assertFalse(rows[0]["allowed"])
        self.assertEqual(rows[0]["reason"], "no_final_signal")
        self.assertEqual(rows[0]["detail"], "side=None mode=None")
        self.assertFalse(rows[0]["dispatch_attempted"])
        self.assertFalse(rows[0]["send_signal_called"])
        self.assertTrue(rows[0]["audit_only"])


if __name__ == "__main__":
    unittest.main()
