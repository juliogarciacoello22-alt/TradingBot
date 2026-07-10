import json
import tempfile
import unittest
from pathlib import Path

from tools.sim101_readiness import run_sim101_readiness


class Sim101ReadinessTests(unittest.TestCase):
    def _safe_env(self):
        return {
            "RUN_MODE": "PAPER",
            "ENABLE_TRADING": "true",
            "TRADING_ACCOUNT": "Sim101",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

    def _write_evidence(self, path: Path, **overrides):
        data = {
            "account": "Sim101",
            "dispatch_attempted": False,
            "dry_run_only": True,
            "orders_sent": 0,
            "passed": True,
            "run_mode": "PAPER",
            "status": "PASS",
            "telegram_connected": False,
            "websocket_connected": False,
        }
        data.update(overrides)
        path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def test_safe_configuration_and_valid_evidence_pass(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = root / "evidence.json"
            dry_run_report = root / "dry-run.json"
            self._write_evidence(evidence)

            result = run_sim101_readiness(
                self._safe_env(),
                evidence_path=evidence,
                dry_run_report_path=dry_run_report,
            )

        self.assertTrue(result.passed)
        self.assertTrue(all(check.passed for check in result.checks))

    def test_missing_evidence_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            result = run_sim101_readiness(
                self._safe_env(),
                evidence_path=root / "missing.json",
                dry_run_report_path=root / "dry-run.json",
            )

        self.assertFalse(result.passed)
        failed = {
            check.name
            for check in result.checks
            if not check.passed
        }
        self.assertIn("controlled_evidence_present", failed)

    def test_failed_evidence_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = root / "evidence.json"
            self._write_evidence(evidence, passed=False, status="FAIL")

            result = run_sim101_readiness(
                self._safe_env(),
                evidence_path=evidence,
                dry_run_report_path=root / "dry-run.json",
            )

        self.assertFalse(result.passed)

    def test_live_environment_fails_closed(self):
        env = self._safe_env()
        env["RUN_MODE"] = "LIVE"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = root / "evidence.json"
            self._write_evidence(evidence)

            result = run_sim101_readiness(
                env,
                evidence_path=evidence,
                dry_run_report_path=root / "dry-run.json",
            )

        self.assertFalse(result.passed)

    def test_real_account_environment_fails_closed(self):
        env = self._safe_env()
        env["TRADING_ACCOUNT"] = "REAL_ACCOUNT_123"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = root / "evidence.json"
            self._write_evidence(evidence)

            result = run_sim101_readiness(
                env,
                evidence_path=evidence,
                dry_run_report_path=root / "dry-run.json",
            )

        self.assertFalse(result.passed)

    def test_evidence_with_dispatch_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            evidence = root / "evidence.json"
            self._write_evidence(
                evidence,
                dispatch_attempted=True,
            )

            result = run_sim101_readiness(
                self._safe_env(),
                evidence_path=evidence,
                dry_run_report_path=root / "dry-run.json",
            )

        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
