import json
import tempfile
import unittest
from pathlib import Path

from tools.sim101_go_no_go import evaluate_sim101_go_no_go


class Sim101GoNoGoTests(unittest.TestCase):
    def _write_json(self, path: Path, data: dict):
        path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def _dry_run_data(self):
        return {
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

    def _controller_data(self):
        return {
            "account": "Sim101",
            "controller_only": True,
            "dispatch_attempted": False,
            "ninjatrader_connected": False,
            "orders_sent": 0,
            "passed": True,
            "readiness_passed": True,
            "run_mode": "PAPER",
            "server_started": False,
            "status": "PASS",
            "telegram_connected": False,
            "websocket_connected": False,
        }

    def test_valid_evidence_returns_go(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dry_run = root / "dry-run.json"
            controller = root / "controller.json"

            self._write_json(dry_run, self._dry_run_data())
            self._write_json(controller, self._controller_data())

            result = evaluate_sim101_go_no_go(
                dry_run,
                controller,
            )

        self.assertTrue(result.passed)
        self.assertEqual(result.decision, "GO")
        self.assertTrue(all(check.passed for check in result.checks))

    def test_missing_evidence_returns_no_go(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            result = evaluate_sim101_go_no_go(
                root / "missing-dry-run.json",
                root / "missing-controller.json",
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.decision, "NO-GO")

    def test_dry_run_dispatch_returns_no_go(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dry_run = root / "dry-run.json"
            controller = root / "controller.json"

            dry_run_data = self._dry_run_data()
            dry_run_data["dispatch_attempted"] = True

            self._write_json(dry_run, dry_run_data)
            self._write_json(controller, self._controller_data())

            result = evaluate_sim101_go_no_go(
                dry_run,
                controller,
            )

        self.assertFalse(result.passed)
        self.assertEqual(result.decision, "NO-GO")

    def test_controller_started_server_returns_no_go(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dry_run = root / "dry-run.json"
            controller = root / "controller.json"

            controller_data = self._controller_data()
            controller_data["server_started"] = True

            self._write_json(dry_run, self._dry_run_data())
            self._write_json(controller, controller_data)

            result = evaluate_sim101_go_no_go(
                dry_run,
                controller,
            )

        self.assertFalse(result.passed)

    def test_controller_ninjatrader_connection_returns_no_go(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dry_run = root / "dry-run.json"
            controller = root / "controller.json"

            controller_data = self._controller_data()
            controller_data["ninjatrader_connected"] = True

            self._write_json(dry_run, self._dry_run_data())
            self._write_json(controller, controller_data)

            result = evaluate_sim101_go_no_go(
                dry_run,
                controller,
            )

        self.assertFalse(result.passed)

    def test_live_mode_returns_no_go(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dry_run = root / "dry-run.json"
            controller = root / "controller.json"

            controller_data = self._controller_data()
            controller_data["run_mode"] = "LIVE"

            self._write_json(dry_run, self._dry_run_data())
            self._write_json(controller, controller_data)

            result = evaluate_sim101_go_no_go(
                dry_run,
                controller,
            )

        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
