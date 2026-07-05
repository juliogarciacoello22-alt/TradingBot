import contextlib
import io
import unittest

from core.runtime_guard import (
    evaluate_signal_permission,
    sync_api_runtime_mode,
    validate_runtime_safety,
)


class _FakePipeline:
    def __init__(self):
        self.is_live = True


class _FakeAPI:
    def __init__(self):
        self.pipeline = _FakePipeline()


class RuntimeGuardTests(unittest.TestCase):
    def test_playback_trading_disabled_playback_account_is_safe_to_start(self):
        env = {
            "RUN_MODE": "PLAYBACK",
            "EnableTrading": "false",
            "TRADING_ACCOUNT": "playback",
        }

        safety = validate_runtime_safety(env)
        permission = evaluate_signal_permission({}, env)

        self.assertTrue(safety.startup_allowed)
        self.assertFalse(safety.live_allowed)
        self.assertEqual(safety.reason, "safe_mode")
        self.assertFalse(permission.allowed)
        self.assertEqual(permission.reason, "enable_trading_disabled")

    def test_live_with_trading_disabled_is_not_live_allowed(self):
        env = {
            "RUN_MODE": "LIVE",
            "EnableTrading": "false",
            "TRADING_ACCOUNT": "real-account",
            "LIVE_TRADING_APPROVED": "true",
        }

        safety = validate_runtime_safety(env)
        permission = evaluate_signal_permission({}, env)

        self.assertTrue(safety.startup_allowed)
        self.assertFalse(safety.live_allowed)
        self.assertEqual(safety.reason, "live_trading_disabled")
        self.assertFalse(permission.allowed)
        self.assertEqual(permission.reason, "enable_trading_disabled")

    def test_live_real_account_without_explicit_approval_is_blocked(self):
        env = {
            "RUN_MODE": "LIVE",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "real-account",
        }

        safety = validate_runtime_safety(env)
        permission = evaluate_signal_permission({}, env)

        self.assertFalse(safety.startup_allowed)
        self.assertFalse(safety.live_allowed)
        self.assertEqual(safety.reason, "live_trading_not_approved")
        self.assertFalse(permission.allowed)
        self.assertEqual(permission.reason, "live_trading_not_approved")

    def test_safe_mode_blocks_real_account_when_trading_is_enabled(self):
        env = {
            "RUN_MODE": "PAPER",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "real-account",
        }

        safety = validate_runtime_safety(env)
        permission = evaluate_signal_permission({}, env)

        self.assertTrue(safety.startup_allowed)
        self.assertFalse(safety.live_allowed)
        self.assertEqual(safety.reason, "safe_mode_blocks_real_account")
        self.assertFalse(permission.allowed)
        self.assertEqual(permission.reason, "paper_live_requires_sim_account")

    def test_telegram_flag_does_not_affect_trading_safety(self):
        base_env = {
            "RUN_MODE": "PLAYBACK",
            "EnableTrading": "false",
            "TRADING_ACCOUNT": "playback",
        }
        telegram_false_env = base_env | {"TELEGRAM_ENABLED": "false"}

        self.assertEqual(
            validate_runtime_safety(base_env).to_dict(),
            validate_runtime_safety(telegram_false_env).to_dict(),
        )

    def test_malformed_boolean_values_are_blocked(self):
        bad_enable_env = {
            "RUN_MODE": "PLAYBACK",
            "EnableTrading": "maybe",
            "TRADING_ACCOUNT": "playback",
        }
        bad_approval_env = {
            "RUN_MODE": "LIVE",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "real-account",
            "LIVE_TRADING_APPROVED": "maybe",
        }

        self.assertEqual(
            validate_runtime_safety(bad_enable_env).reason,
            "malformed_enable_trading",
        )
        self.assertEqual(
            validate_runtime_safety(bad_approval_env).reason,
            "malformed_live_trading_approved",
        )
        self.assertFalse(evaluate_signal_permission({}, bad_enable_env).allowed)
        self.assertFalse(evaluate_signal_permission({}, bad_approval_env).allowed)

    def test_sync_forces_pipeline_safe_when_live_is_not_approved(self):
        api = _FakeAPI()
        env = {
            "RUN_MODE": "LIVE",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "real-account",
        }

        with contextlib.redirect_stdout(io.StringIO()):
            run_mode = sync_api_runtime_mode(api, env)

        self.assertEqual(run_mode, "LIVE")
        self.assertFalse(api.is_live)
        self.assertFalse(api.pipeline.is_live)
        self.assertEqual(api.runtime_safety.reason, "live_trading_not_approved")


if __name__ == "__main__":
    unittest.main()
