import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.stream_ping_smoke import run_stream_ping_smoke


class StreamPingSmokeTests(unittest.TestCase):
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
        "tools.stream_ping_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_successful_ping_returns_pass(self, controlled_codes):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()
            with (
                patch("tools.stream_ping_smoke.subprocess.Popen", return_value=process),
                patch("tools.stream_ping_smoke._find_free_port", return_value=8765),
                patch("tools.stream_ping_smoke._wait_for_http", return_value=True),
                patch(
                    "tools.stream_ping_smoke._stream_ping_round_trip",
                    return_value=(True, True, False),
                ),
            ):
                result = run_stream_ping_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertTrue(result.passed)
        self.assertTrue(result.stream_connected)
        self.assertTrue(result.ping_sent)
        self.assertTrue(result.no_response_expected)
        self.assertFalse(result.unexpected_response_received)
        self.assertTrue(result.stream_closed)
        self.assertFalse(result.dispatch_attempted)
        self.assertFalse(result.pipeline_invoked)
        self.assertEqual(result.signals_sent, 0)
        self.assertEqual(result.orders_sent, 0)
        self.assertFalse(result.real_ninjatrader_connected)

    @patch(
        "tools.stream_ping_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_unexpected_response_returns_fail(self, controlled_codes):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()
            with (
                patch("tools.stream_ping_smoke.subprocess.Popen", return_value=process),
                patch("tools.stream_ping_smoke._find_free_port", return_value=8765),
                patch("tools.stream_ping_smoke._wait_for_http", return_value=True),
                patch(
                    "tools.stream_ping_smoke._stream_ping_round_trip",
                    return_value=(True, True, True),
                ),
            ):
                result = run_stream_ping_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "unexpected_stream_response")

    @patch(
        "tools.stream_ping_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_http_timeout_skips_stream(self, controlled_codes):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()
            with (
                patch("tools.stream_ping_smoke.subprocess.Popen", return_value=process),
                patch("tools.stream_ping_smoke._find_free_port", return_value=8765),
                patch("tools.stream_ping_smoke._wait_for_http", return_value=False),
                patch("tools.stream_ping_smoke._stream_ping_round_trip") as round_trip,
            ):
                result = run_stream_ping_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "server_not_ready_before_timeout")
        round_trip.assert_not_called()

    @patch(
        "tools.stream_ping_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_stream_exception_fails_closed(self, controlled_codes):
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()
            with (
                patch("tools.stream_ping_smoke.subprocess.Popen", return_value=process),
                patch("tools.stream_ping_smoke._find_free_port", return_value=8765),
                patch("tools.stream_ping_smoke._wait_for_http", return_value=True),
                patch(
                    "tools.stream_ping_smoke._stream_ping_round_trip",
                    side_effect=ConnectionError("boom"),
                ),
            ):
                result = run_stream_ping_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertEqual(result.reason, "stream_ping_smoke_exception:ConnectionError")
        self.assertFalse(result.dispatch_attempted)
        self.assertFalse(result.pipeline_invoked)

    @patch(
        "tools.stream_ping_smoke._controlled_shutdown_codes",
        return_value={0, 1},
    )
    def test_environment_is_not_modified(self, controlled_codes):
        env = self._safe_env()
        original = dict(env)
        with tempfile.TemporaryDirectory() as temp_dir:
            process = self._running_process()
            with (
                patch("tools.stream_ping_smoke.subprocess.Popen", return_value=process),
                patch("tools.stream_ping_smoke._find_free_port", return_value=8765),
                patch("tools.stream_ping_smoke._wait_for_http", return_value=True),
                patch(
                    "tools.stream_ping_smoke._stream_ping_round_trip",
                    return_value=(True, True, False),
                ),
            ):
                run_stream_ping_smoke(
                    env,
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertEqual(env, original)

    def test_startup_exception_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch(
                    "tools.stream_ping_smoke.subprocess.Popen",
                    side_effect=OSError("boom"),
                ),
                patch("tools.stream_ping_smoke._find_free_port", return_value=8765),
            ):
                result = run_stream_ping_smoke(
                    self._safe_env(),
                    report_path=Path(temp_dir) / "report.json",
                )

        self.assertFalse(result.passed)
        self.assertFalse(result.dispatch_attempted)
        self.assertFalse(result.pipeline_invoked)
        self.assertEqual(result.orders_sent, 0)


if __name__ == "__main__":
    unittest.main()
