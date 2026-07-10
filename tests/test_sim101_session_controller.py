import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.sim101_session_controller import (
    main,
    run_sim101_session_controller,
)


class Sim101SessionControllerTests(unittest.TestCase):
    def _safe_env(self):
        return {
            "RUN_MODE": "PAPER",
            "ENABLE_TRADING": "true",
            "TRADING_ACCOUNT": "Sim101",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

    def _readiness_result(self, passed=True):
        return SimpleNamespace(
            passed=passed,
            to_dict=lambda: {
                "passed": passed,
                "checks": [],
            },
        )

    def test_readiness_pass_generates_safe_controller_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "controller.json"

            with patch(
                "tools.sim101_session_controller.run_sim101_readiness",
                return_value=self._readiness_result(True),
            ) as readiness_mock:
                result = run_sim101_session_controller(
                    self._safe_env(),
                    report_path=report_path,
                    started_at_utc="2026-07-10T12:00:00+00:00",
                )

            self.assertTrue(result.passed)
            self.assertEqual(result.status, "PASS")
            self.assertEqual(result.reason, "readiness_passed")
            readiness_mock.assert_called_once()

            report = json.loads(
                report_path.read_text(encoding="utf-8")
            )

            self.assertTrue(report["controller_only"])
            self.assertFalse(report["server_started"])
            self.assertFalse(report["dispatch_attempted"])
            self.assertFalse(report["websocket_connected"])
            self.assertFalse(report["ninjatrader_connected"])
            self.assertFalse(report["telegram_connected"])
            self.assertEqual(report["orders_sent"], 0)

    def test_readiness_fail_returns_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "tools.sim101_session_controller.run_sim101_readiness",
                return_value=self._readiness_result(False),
            ):
                result = run_sim101_session_controller(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "controller.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(result.reason, "readiness_failed")
        self.assertFalse(result.server_started)
        self.assertFalse(result.dispatch_attempted)
        self.assertEqual(result.orders_sent, 0)

    def test_readiness_exception_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "tools.sim101_session_controller.run_sim101_readiness",
                side_effect=RuntimeError("boom"),
            ):
                result = run_sim101_session_controller(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "controller.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(result.status, "FAIL")
        self.assertEqual(
            result.reason,
            "readiness_exception:RuntimeError",
        )
        self.assertFalse(result.server_started)
        self.assertFalse(result.dispatch_attempted)
        self.assertEqual(result.orders_sent, 0)

    def test_input_environment_is_not_modified(self):
        env = self._safe_env()
        original = dict(env)

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "tools.sim101_session_controller.run_sim101_readiness",
                return_value=self._readiness_result(True),
            ):
                run_sim101_session_controller(
                    env,
                    report_path=Path(temp_dir) / "controller.json",
                )

        self.assertEqual(env, original)

    def test_live_mode_does_not_change_safety_boundaries(self):
        env = self._safe_env()
        env["RUN_MODE"] = "LIVE"

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "tools.sim101_session_controller.run_sim101_readiness",
                return_value=self._readiness_result(False),
            ):
                result = run_sim101_session_controller(
                    env,
                    report_path=Path(temp_dir) / "controller.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(result.run_mode, "LIVE")
        self.assertFalse(result.server_started)
        self.assertFalse(result.dispatch_attempted)
        self.assertFalse(result.ninjatrader_connected)
        self.assertEqual(result.orders_sent, 0)

    def test_main_returns_zero_when_readiness_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "controller.json"

            with patch(
                "tools.sim101_session_controller."
                "run_sim101_session_controller"
            ) as controller_mock:
                controller_mock.return_value = SimpleNamespace(
                    passed=True,
                    to_dict=lambda: {
                        "passed": True,
                        "status": "PASS",
                    },
                )

                exit_code = main(
                    [
                        "--report",
                        str(report_path),
                    ]
                )

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
