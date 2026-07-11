import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.pipeline_live_pro import _decision_log, _terminal_decision_fields


class PipelineStructuredTerminalReasonsTests(unittest.TestCase):
    def test_valid_entry_failure_includes_specific_subreason(self):
        fields = _terminal_decision_fields(
            signal_engine=SimpleNamespace(
                last_build_signal_reason="valid_entry_failed",
                last_valid_entry_reason="mitigation_light_true",
            ),
            ob_engine=SimpleNamespace(
                last_decision_reason="ok",
                last_decision_detail="type=bullish valid=False",
            ),
            timing={"valid": True, "reason": "ok"},
        )
        self.assertEqual(fields["terminal_stage"], "build_signal")
        self.assertEqual(fields["terminal_reason"], "valid_entry_failed")
        self.assertEqual(fields["terminal_subreason"], "mitigation_light_true")
        self.assertEqual(fields["ob_reason"], "ok")

    def test_timing_failure_includes_deadzone_subreason(self):
        fields = _terminal_decision_fields(
            signal_engine=SimpleNamespace(
                last_build_signal_reason="timing_invalid",
                last_valid_entry_reason="entry_filters_passed",
            ),
            ob_engine=SimpleNamespace(
                last_decision_reason="raw_ob_missing",
                last_decision_detail="candles=81",
            ),
            timing={"valid": False, "reason": "deadzone"},
        )
        self.assertEqual(fields["terminal_reason"], "timing_invalid")
        self.assertEqual(fields["terminal_subreason"], "deadzone")
        self.assertEqual(fields["ob_reason"], "raw_ob_missing")
        self.assertEqual(fields["timing_reason"], "deadzone")

    def test_explicit_execution_terminal_reason_is_preserved(self):
        fields = _terminal_decision_fields(
            signal_engine=SimpleNamespace(
                last_build_signal_reason="scalper_generated",
                last_valid_entry_reason="entry_filters_passed",
            ),
            ob_engine=SimpleNamespace(
                last_decision_reason="ok",
                last_decision_detail="type=bullish valid=True",
            ),
            timing={"valid": True, "reason": "ok"},
            terminal_stage="execution_engine",
            terminal_reason="execution_rejected",
            terminal_subreason="invalid_stop",
        )
        self.assertEqual(fields["terminal_stage"], "execution_engine")
        self.assertEqual(fields["terminal_reason"], "execution_rejected")
        self.assertEqual(fields["terminal_subreason"], "invalid_stop")

    def test_decision_log_preserves_legacy_and_structured_fields(self):
        with (
            patch("core.pipeline_live_pro.audit_session_logger.get_session_id", return_value="session-test"),
            patch("core.pipeline_live_pro.audit_session_logger.append_jsonl") as append_jsonl,
        ):
            _decision_log(
                "process",
                False,
                "no_final_signal",
                "side=None mode=None",
                terminal_stage="build_signal",
                terminal_reason="valid_entry_failed",
                terminal_subreason="missing_momentum",
                ob_reason="raw_ob_missing",
            )
        filename, payload = append_jsonl.call_args.args
        self.assertEqual(filename, "pipeline_decisions.jsonl")
        self.assertEqual(payload["reason"], "no_final_signal")
        self.assertFalse(payload["allowed"])
        self.assertFalse(payload["dispatch_attempted"])
        self.assertFalse(payload["send_signal_called"])
        self.assertTrue(payload["audit_only"])
        self.assertEqual(payload["terminal_stage"], "build_signal")
        self.assertEqual(payload["terminal_reason"], "valid_entry_failed")
        self.assertEqual(payload["terminal_subreason"], "missing_momentum")
        self.assertEqual(payload["ob_reason"], "raw_ob_missing")

    def test_none_structured_fields_are_omitted(self):
        with (
            patch("core.pipeline_live_pro.audit_session_logger.get_session_id", return_value="session-test"),
            patch("core.pipeline_live_pro.audit_session_logger.append_jsonl") as append_jsonl,
        ):
            _decision_log("process", False, "exception", "boom", terminal_reason=None)
        payload = append_jsonl.call_args.args[1]
        self.assertNotIn("terminal_reason", payload)


if __name__ == "__main__":
    unittest.main()
