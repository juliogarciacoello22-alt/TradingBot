import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.internal_websocket_smoke import (
    run_internal_websocket_smoke,
)


class InternalWebSocketSmokeTests(unittest.TestCase):
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
        process.communicate.return_value = ("", "")
        return process

    @patch(
        "tools.internal_websocket_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_successful_round_trip_returns_pass(self, controlled_codes):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()

            with (
                patch(
                    "tools.internal_websocket_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.internal_websocket_smoke._find_free_port",
                    return_value=8765,
                ),
                patch(
                    "tools.internal_websocket_smoke._wait_for_http",
                    return_value=True,
                ),
                patch(
                    "tools.internal_websocket_smoke."
                    "_websocket_round_trip",
                    return_value="OK",
                ) as round_trip,
            ):
                result = run_internal_websocket_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertTrue(result.passed)
        self.assertEqual(result.status, "PASS")
        self.assertTrue(result.websocket_connected)
        self.assertTrue(result.message_sent)
        self.assertTrue(result.response_received)
        self.assertEqual(result.response_text, "OK")
        self.assertTrue(result.websocket_closed)
        self.assertFalse(result.dispatch_attempted)
        self.assertEqual(result.orders_sent, 0)
        self.assertFalse(result.stream_connected)
        self.assertFalse(result.ninjatrader_connected)
        self.assertFalse(result.telegram_connected)
        round_trip.assert_called_once()

    @patch(
        "tools.internal_websocket_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_unexpected_response_returns_fail(self, controlled_codes):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()

            with (
                patch(
                    "tools.internal_websocket_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.internal_websocket_smoke._find_free_port",
                    return_value=8765,
                ),
                patch(
                    "tools.internal_websocket_smoke._wait_for_http",
                    return_value=True,
                ),
                patch(
                    "tools.internal_websocket_smoke."
                    "_websocket_round_trip",
                    return_value="NOT_OK",
                ),
            ):
                result = run_internal_websocket_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "unexpected_websocket_response",
        )

    @patch(
        "tools.internal_websocket_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_http_timeout_does_not_open_websocket(
        self,
        controlled_codes,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()

            with (
                patch(
                    "tools.internal_websocket_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.internal_websocket_smoke._find_free_port",
                    return_value=8765,
                ),
                patch(
                    "tools.internal_websocket_smoke._wait_for_http",
                    return_value=False,
                ),
                patch(
                    "tools.internal_websocket_smoke."
                    "_websocket_round_trip"
                ) as round_trip,
            ):
                result = run_internal_websocket_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "server_not_ready_before_timeout",
        )
        round_trip.assert_not_called()

    @patch(
        "tools.internal_websocket_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_websocket_exception_fails_closed(
        self,
        controlled_codes,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()

            with (
                patch(
                    "tools.internal_websocket_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.internal_websocket_smoke._find_free_port",
                    return_value=8765,
                ),
                patch(
                    "tools.internal_websocket_smoke._wait_for_http",
                    return_value=True,
                ),
                patch(
                    "tools.internal_websocket_smoke."
                    "_websocket_round_trip",
                    side_effect=ConnectionError("boom"),
                ),
            ):
                result = run_internal_websocket_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "websocket_smoke_exception:ConnectionError",
        )
        self.assertFalse(result.dispatch_attempted)
        self.assertEqual(result.orders_sent, 0)

    @patch(
        "tools.internal_websocket_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_environment_is_not_modified(self, controlled_codes):
        env = self._safe_env()
        original = dict(env)

        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()

            with (
                patch(
                    "tools.internal_websocket_smoke.subprocess.Popen",
                    return_value=process,
                ),
                patch(
                    "tools.internal_websocket_smoke._find_free_port",
                    return_value=8765,
                ),
                patch(
                    "tools.internal_websocket_smoke._wait_for_http",
                    return_value=True,
                ),
                patch(
                    "tools.internal_websocket_smoke."
                    "_websocket_round_trip",
                    return_value="OK",
                ),
            ):
                run_internal_websocket_smoke(
                    env,
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertEqual(env, original)

    def test_startup_exception_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch(
                    "tools.internal_websocket_smoke.subprocess.Popen",
                    side_effect=OSError("boom"),
                ),
                patch(
                    "tools.internal_websocket_smoke._find_free_port",
                    return_value=8765,
                ),
            ):
                result = run_internal_websocket_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertFalse(result.dispatch_attempted)
        self.assertEqual(result.orders_sent, 0)
        self.assertFalse(result.ninjatrader_connected)


if __name__ == "__main__":
    unittest.main()
