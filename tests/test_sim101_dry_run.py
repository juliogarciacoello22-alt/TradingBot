import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.sim101_dry_run import main, run_sim101_dry_run


class Sim101DryRunTests(unittest.TestCase):
    def _safe_env(self):
        return {
            "RUN_MODE": "PAPER",
            "ENABLE_TRADING": "true",
            "TRADING_ACCOUNT": "Sim101",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

    def test_safe_configuration_generates_pass_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"

            result = run_sim101_dry_run(
                self._safe_env(),
                report_path=report_path,
                started_at_utc="2026-07-10T12:00:00+00:00",
            )

            self.assertTrue(result.passed)
            self.assertEqual(result.status, "PASS")
            self.assertTrue(report_path.exists())

            report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertTrue(report["dry_run_only"])
            self.assertFalse(report["dispatch_attempted"])
            self.assertFalse(report["websocket_connected"])
            self.assertFalse(report["telegram_connected"])
            self.assertEqual(report["orders_sent"], 0)
            self.assertTrue(report["preflight"]["passed"])

    def test_failed_preflight_generates_fail_report(self):
        env = self._safe_env()
        env["EnableTrading"] = "false"

        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"

            result = run_sim101_dry_run(
                env,
                report_path=report_path,
            )

            self.assertFalse(result.passed)
            self.assertEqual(result.status, "FAIL")
            self.assertTrue(report_path.exists())

            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(report["preflight"]["passed"])
            self.assertFalse(report["dispatch_attempted"])
            self.assertEqual(report["orders_sent"], 0)

    def test_live_mode_fails_closed(self):
        env = self._safe_env()
        env["RUN_MODE"] = "LIVE"

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_sim101_dry_run(
                env,
                report_path=Path(temp_dir) / "report.json",
            )

        self.assertFalse(result.passed)
        self.assertFalse(result.dispatch_attempted)
        self.assertEqual(result.orders_sent, 0)

    def test_non_sim101_account_fails_closed(self):
        env = self._safe_env()
        env["TRADING_ACCOUNT"] = "REAL_ACCOUNT_123"

        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_sim101_dry_run(
                env,
                report_path=Path(temp_dir) / "report.json",
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.account, "REAL_ACCOUNT_123")
        self.assertFalse(result.dispatch_attempted)

    def test_input_environment_is_not_modified(self):
        env = self._safe_env()
        original = dict(env)

        with tempfile.TemporaryDirectory() as temp_dir:
            run_sim101_dry_run(
                env,
                report_path=Path(temp_dir) / "report.json",
            )

        self.assertEqual(env, original)

    def test_main_returns_zero_for_safe_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"

            with patch.dict(os.environ, self._safe_env(), clear=True):
                exit_code = main(
                    ["--report", str(report_path)]
                )

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
