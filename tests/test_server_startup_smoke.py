import json
import subprocess
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

    def _running_process(self, return_code=1):
        process = Mock()
        process.poll.side_effect = [None, None, return_code]
        process.returncode = return_code
        process.communicate.return_value = (
            "controlled stdout",
            "controlled stderr",
        )
        return process

    def _stopped_process(self, return_code=1):
        process = Mock()
        process.poll.side_effect = [
            return_code,
            return_code,
            return_code,
        ]
        process.returncode = return_code
        process.communicate.return_value = (
            "startup stdout",
            "startup stderr",
        )
        return process

    @patch(
        "tools.server_startup_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_successful_startup_and_controlled_shutdown_returns_pass(
        self,
        controlled_codes,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            process = self._running_process(return_code=1)

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
            self.assertTrue(result.startup_passed)
            self.assertTrue(result.shutdown_passed)
            self.assertTrue(result.shutdown_requested)
            self.assertEqual(result.shutdown_method, "terminate")
            self.assertFalse(result.shutdown_timed_out)
            self.assertEqual(result.return_code, 1)
            self.assertEqual(result.stdout, "controlled stdout")
            self.assertEqual(result.stderr, "controlled stderr")
            self.assertEqual(
                result.reason,
                "server_started_responded_and_stopped",
            )

            process.terminate.assert_called_once()
            process.kill.assert_not_called()
            process.communicate.assert_called_once_with(timeout=5)

            report = json.loads(
                report_path.read_text(encoding="utf-8")
            )

            self.assertTrue(report["startup_passed"])
            self.assertTrue(report["shutdown_passed"])
            self.assertFalse(report["dispatch_attempted"])
            self.assertEqual(report["orders_sent"], 0)
            self.assertFalse(report["websocket_connected"])
            self.assertFalse(report["ninjatrader_connected"])
            self.assertFalse(report["telegram_connected"])

    @patch(
        "tools.server_startup_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_http_timeout_returns_fail_but_shutdown_is_controlled(
        self,
        controlled_codes,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process(return_code=1)

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
        self.assertFalse(result.startup_passed)
        self.assertTrue(result.shutdown_passed)
        self.assertEqual(
            result.reason,
            "server_not_ready_before_timeout",
        )

    def test_process_start_failure_returns_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._stopped_process(return_code=1)

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
        self.assertFalse(result.startup_passed)
        self.assertFalse(result.shutdown_passed)
        self.assertFalse(result.shutdown_requested)
        self.assertEqual(result.shutdown_method, "none")
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
        self.assertFalse(result.startup_passed)
        self.assertFalse(result.shutdown_passed)
        self.assertEqual(
            result.reason,
            "startup_exception:OSError",
        )
        self.assertFalse(result.dispatch_attempted)
        self.assertEqual(result.orders_sent, 0)

    @patch(
        "tools.server_startup_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_shutdown_timeout_uses_kill_and_fails_clean_shutdown(
        self,
        controlled_codes,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process(return_code=1)
            process.communicate.side_effect = [
                subprocess.TimeoutExpired(
                    cmd="uvicorn",
                    timeout=5,
                ),
                ("stdout after kill", "stderr after kill"),
            ]

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
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertTrue(result.startup_passed)
        self.assertFalse(result.shutdown_passed)
        self.assertTrue(result.shutdown_requested)
        self.assertTrue(result.shutdown_timed_out)
        self.assertEqual(result.shutdown_method, "kill")
        self.assertEqual(
            result.reason,
            "server_started_but_shutdown_failed",
        )
        process.kill.assert_called_once()

    @patch(
        "tools.server_startup_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_input_environment_is_not_modified(
        self,
        controlled_codes,
    ):
        env = self._safe_env()
        original = dict(env)

        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process(return_code=1)

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

    @patch(
        "tools.server_startup_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_live_mode_does_not_change_passive_boundaries(
        self,
        controlled_codes,
    ):
        env = self._safe_env()
        env["RUN_MODE"] = "LIVE"

        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process(return_code=1)

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
