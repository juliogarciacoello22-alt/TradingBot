import unittest

from tools.sim101_preflight import run_sim101_preflight


class Sim101PreflightTests(unittest.TestCase):
    def test_exact_safe_sim101_configuration_passes(self):
        env = {
            "RUN_MODE": "PAPER",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "Sim101",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

        result = run_sim101_preflight(env)

        self.assertTrue(result.passed)
        self.assertTrue(all(check.passed for check in result.checks))

    def test_disabled_trading_fails(self):
        env = {
            "RUN_MODE": "PAPER",
            "EnableTrading": "false",
            "TRADING_ACCOUNT": "Sim101",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

        result = run_sim101_preflight(env)

        self.assertFalse(result.passed)
        failed = {
            check.name
            for check in result.checks
            if not check.passed
        }
        self.assertIn("trading_explicitly_enabled", failed)
        self.assertIn("signal_permission_allowed", failed)

    def test_live_mode_fails_even_with_sim101(self):
        env = {
            "RUN_MODE": "LIVE",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "Sim101",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

        result = run_sim101_preflight(env)

        self.assertFalse(result.passed)
        failed = {
            check.name
            for check in result.checks
            if not check.passed
        }
        self.assertIn("run_mode_is_paper", failed)
        self.assertIn("signal_permission_allowed", failed)

    def test_real_account_fails(self):
        env = {
            "RUN_MODE": "PAPER",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "REAL_ACCOUNT_123",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

        result = run_sim101_preflight(env)

        self.assertFalse(result.passed)
        failed = {
            check.name
            for check in result.checks
            if not check.passed
        }
        self.assertIn("account_is_exact_sim101", failed)
        self.assertIn("account_is_not_real", failed)
        self.assertIn("signal_permission_allowed", failed)

    def test_telegram_enabled_fails(self):
        env = {
            "RUN_MODE": "PAPER",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "Sim101",
            "TELEGRAM_ENABLED": "true",
            "LIVE_TRADING_APPROVED": "false",
        }

        result = run_sim101_preflight(env)

        self.assertFalse(result.passed)
        failed = {
            check.name
            for check in result.checks
            if not check.passed
        }
        self.assertIn("telegram_disabled", failed)

    def test_missing_values_fail_closed(self):
        result = run_sim101_preflight({})

        self.assertFalse(result.passed)
        self.assertTrue(any(not check.passed for check in result.checks))


if __name__ == "__main__":
    unittest.main()
