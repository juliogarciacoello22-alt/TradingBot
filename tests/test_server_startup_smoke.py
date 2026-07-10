import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.server_startup_smoke import run_server_startup_smoke


class ServerStartupSmokeTests(unittest.TestCase):
    def _safe_env(self):
        return {
            "RUN_MODE": "PLAYBACK",
            "ENABLE_TRADING": "false",
            "TRADING_ACCOUNT": "playback",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

    def _process_mock(self, initial_poll=None, return_code=0):
        process = Mock()
        process.poll.side_effect = [
            initial_poll,
            initial_poll,
            return_code,
        ]
        process.returncode = return_code
        process.wait.return_value = return_code
        return process

    def test_successful_startup_returns_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            process = self._process_mock()

            with (
                patch(
                    "tools.server_startup_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.server_startup_smoke._wait_for_http",
                    return_value=True,
                ),
                patch(
                    "tools.server_startup_smoke._find_free_port",
                    return_value=8765,
                ),
            ):
                result = run_server_startup_smoke(
                    self._safe_env(),
                    report_path=report_path,
                )

            self.assertTrue(result.passed)
            self.assertEqual(result.status, "PASS")
            self.assertTrue(result.process_started)
            self.assertTrue(result.http_ready)
            self.assertTrue(result.process_stopped)

            report = json.loads(
                report_path.read_text(encoding="utf-8")
            )

            self.assertFalse(report["dispatch_attempted"])
            self.assertEqual(report["orders_sent"], 0)
            self.assertFalse(report["websocket_connected"])
            self.assertFalse(report["ninjatrader_connected"])
            self.assertFalse(report["telegram_connected"])

    def test_http_timeout_returns_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._process_mock()

            with (
                patch(
                    "tools.server_startup_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.server_startup_smoke._wait_for_http",
                    return_value=False,
                ),
                patch(
                    "tools.server_startup_smoke._find_free_port",
                    return_value=8765,
                ),
            ):
                result = run_server_startup_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "server_not_ready_before_timeout",
        )

    def test_process_start_failure_returns_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._process_mock(
                initial_poll=1,
                return_code=1,
            )

            with (
                patch(
                    "tools.server_startup_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.server_startup_smoke._find_free_port",
                    return_value=8765,
                ),
            ):
                result = run_server_startup_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "process_failed_to_start")

    def test_startup_exception_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch(
                    "tools.server_startup_smoke.subprocess.Popen",
                    side_effect=OSError("boom"),
                ),
                patch(
                    "tools.server_startup_smoke._find_free_port",
                    return_value=8765,
                ),
            ):
                result = run_server_startup_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "startup_exception:OSError",
        )
        self.assertFalse(result.dispatch_attempted)
        self.assertEqual(result.orders_sent, 0)

    def test_input_environment_is_not_modified(self):
        env = self._safe_env()
        original = dict(env)

        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._process_mock()

            with (
                patch(
                    "tools.server_startup_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.server_startup_smoke._wait_for_http",
                    return_value=True,
                ),
                patch(
                    "tools.server_startup_smoke._find_free_port",
                    return_value=8765,
                ),
            ):
                run_server_startup_smoke(
                    env,
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertEqual(env, original)

    def test_live_mode_does_not_change_passive_boundaries(self):
        env = self._safe_env()
        env["RUN_MODE"] = "LIVE"

        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._process_mock()

            with (
                patch(
                    "tools.server_startup_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.server_startup_smoke._wait_for_http",
                    return_value=True,
                ),
                patch(
                    "tools.server_startup_smoke._find_free_port",
                    return_value=8765,
                ),
            ):
                result = run_server_startup_smoke(
                    env,
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertTrue(result.passed)
        self.assertEqual(result.run_mode, "LIVE")
        self.assertFalse(result.dispatch_attempted)
        self.assertEqual(result.orders_sent, 0)
        self.assertFalse(result.ninjatrader_connected)


if __name__ == "__main__":
    unittest.main()
