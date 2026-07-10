import os
import unittest
from unittest.mock import AsyncMock, patch

from core.api import API


class APIRuntimeGuardDispatchBlockTests(unittest.IsolatedAsyncioTestCase):
    async def test_playback_trading_disabled_blocks_all_delivery(self):
        env = {
            "RUN_MODE": "PLAYBACK",
            "EnableTrading": "false",
            "TRADING_ACCOUNT": "playback",
            "TELEGRAM_ENABLED": "false",
        }
        signal = {
            "side": "BUY",
            "entry": 100.0,
            "stop": 99.0,
            "tp1": 101.0,
        }

        with patch.dict(os.environ, env, clear=False):
            api = API()
            api._send_to_ninjatrader = AsyncMock()
            api._send_to_telegram = AsyncMock()

            with patch("core.api.log_blocked_execution") as blocked_log:
                result = await api.send_signal(signal)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["run_mode"], "PLAYBACK")
        self.assertEqual(result["account"], "playback")
        self.assertEqual(result["reason"], "enable_trading_disabled")
        self.assertFalse(result["enable_trading"])

        api._send_to_ninjatrader.assert_not_awaited()
        api._send_to_telegram.assert_not_awaited()
        blocked_log.assert_called_once()

    async def test_live_trading_disabled_blocks_all_delivery(self):
        env = {
            "RUN_MODE": "LIVE",
            "EnableTrading": "false",
            "TRADING_ACCOUNT": "real-account",
            "LIVE_TRADING_APPROVED": "true",
            "TELEGRAM_ENABLED": "false",
        }
        signal = {
            "side": "SELL",
            "entry": 100.0,
            "stop": 101.0,
            "tp1": 99.0,
        }

        with patch.dict(os.environ, env, clear=False):
            api = API()
            api._send_to_ninjatrader = AsyncMock()
            api._send_to_telegram = AsyncMock()

            with patch("core.api.log_blocked_execution") as blocked_log:
                result = await api.send_signal(signal)

        self.assertFalse(result["allowed"])
        self.assertEqual(result["run_mode"], "LIVE")
        self.assertEqual(result["account"], "real-account")
        self.assertEqual(result["reason"], "enable_trading_disabled")
        self.assertFalse(result["enable_trading"])

        api._send_to_ninjatrader.assert_not_awaited()
        api._send_to_telegram.assert_not_awaited()
        blocked_log.assert_called_once()


if __name__ == "__main__":
    unittest.main()