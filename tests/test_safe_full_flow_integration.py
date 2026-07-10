import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.api import API
from core.pipeline_live_pro import PipelineLivePRO


class SafeFullFlowIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def _build_pipeline(self, api):
        candle = SimpleNamespace(
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000,
            timestamp="2026-07-10T12:00:00Z",
        )

        api.loader = Mock()
        api.loader.load.return_value = {
            "1m": [candle],
            "5m": [candle, candle, candle],
            "30m": [candle],
        }
        api.prev_delta = None

        pipeline = PipelineLivePRO(api, is_live=True)

        pipeline.exit_engine = Mock()
        pipeline.exit_engine.has_open_trade.return_value = False

        pipeline.micro_engine = Mock()
        pipeline.micro_engine.process.return_value = {}

        pipeline.ob_engine = Mock()
        pipeline.ob_engine.detect_ob.return_value = {}

        pipeline.context_engine = Mock()
        pipeline.context_engine.build_context.return_value = {}

        pipeline.timing_engine = Mock()
        pipeline.timing_engine.build_timing.return_value = {
            "valid": True,
        }

        pipeline.forecast_engine = Mock()
        pipeline.forecast_engine.predict.return_value = {}

        signal = {
            "side": "BUY",
            "entry": 100.5,
            "stop": 99.5,
            "tp1": 101.5,
            "meta": {},
        }

        pipeline.signal_engine = Mock()
        pipeline.signal_engine.build_signal.return_value = signal

        pipeline.risk_engine = Mock()
        pipeline.risk_engine.evaluate.return_value = {
            "valid": True,
            "risk_score": 1.0,
            "reason": "ok",
        }

        pipeline.dedup = Mock()
        pipeline.dedup.is_duplicate.return_value = False
        pipeline._log_signal = Mock()

        raw = {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
            "timestamp": "2026-07-10T12:00:00Z",
        }

        return pipeline, signal, raw

    async def _allow_dispatch_task_to_finish(self, dispatched_tasks):
        self.assertEqual(len(dispatched_tasks), 1)

        dispatch_task = dispatched_tasks[0]
        if isinstance(dispatch_task, asyncio.Task):
            await dispatch_task

        # Allow the task done-callback to run.
        await asyncio.sleep(0)

    async def test_paper_sim101_full_flow_dispatches_and_opens_once(self):
        env = {
            "RUN_MODE": "PAPER",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "Sim101",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

        with patch.dict(os.environ, env, clear=False):
            api = API()
            api._send_to_ninjatrader = AsyncMock()
            api._send_to_telegram = AsyncMock()

            pipeline, signal, raw = self._build_pipeline(api)

            dispatched_tasks = []
            real_dispatch = pipeline._dispatch_signal

            def capture_dispatch(signal, on_allowed=None):
                dispatch_task = real_dispatch(
                    signal,
                    on_allowed=on_allowed,
                )
                dispatched_tasks.append(dispatch_task)
                return dispatch_task

            pipeline._dispatch_signal = capture_dispatch

            with (
                patch(
                    "core.pipeline_live_pro.delta_calc.compute_delta",
                    return_value=1.0,
                ),
                patch(
                    "core.pipeline_live_pro.delta_calc.compute_cumdelta",
                    return_value=1.0,
                ),
                patch(
                    "core.pipeline_live_pro.execution_engine.validate",
                    return_value=(True, "ok"),
                ),
                patch("core.pipeline_live_pro.log_institucional_file_basic"),
                patch("core.pipeline_live_pro.log_institucional_file_extended"),
                patch("core.pipeline_live_pro.update_dashboard"),
                patch("core.pipeline_live_pro._emit_full_path_snapshot_audit"),
                patch("core.pipeline_live_pro._decision_log"),
            ):
                result = pipeline.process(raw)
                await self._allow_dispatch_task_to_finish(dispatched_tasks)

        self.assertEqual(result, signal)
        self.assertEqual(api.last_signal, signal)

        api._send_to_ninjatrader.assert_awaited_once_with(signal)
        api._send_to_telegram.assert_awaited_once_with(signal)

        pipeline.exit_engine.open_from_signal.assert_called_once_with(signal)
        pipeline.dedup.is_duplicate.assert_called_once_with(signal)
        pipeline._log_signal.assert_called_once_with(signal)

    async def test_playback_disabled_full_flow_blocks_every_delivery(self):
        env = {
            "RUN_MODE": "PLAYBACK",
            "EnableTrading": "false",
            "TRADING_ACCOUNT": "playback",
            "TELEGRAM_ENABLED": "false",
            "LIVE_TRADING_APPROVED": "false",
        }

        with patch.dict(os.environ, env, clear=False):
            api = API()
            api._send_to_ninjatrader = AsyncMock()
            api._send_to_telegram = AsyncMock()

            pipeline, signal, raw = self._build_pipeline(api)

            dispatched_tasks = []
            real_dispatch = pipeline._dispatch_signal

            def capture_dispatch(signal, on_allowed=None):
                dispatch_task = real_dispatch(
                    signal,
                    on_allowed=on_allowed,
                )
                dispatched_tasks.append(dispatch_task)
                return dispatch_task

            pipeline._dispatch_signal = capture_dispatch

            with (
                patch(
                    "core.pipeline_live_pro.delta_calc.compute_delta",
                    return_value=1.0,
                ),
                patch(
                    "core.pipeline_live_pro.delta_calc.compute_cumdelta",
                    return_value=1.0,
                ),
                patch(
                    "core.pipeline_live_pro.execution_engine.validate",
                    return_value=(True, "ok"),
                ),
                patch("core.pipeline_live_pro.log_institucional_file_basic"),
                patch("core.pipeline_live_pro.log_institucional_file_extended"),
                patch("core.pipeline_live_pro.update_dashboard"),
                patch("core.pipeline_live_pro._emit_full_path_snapshot_audit"),
                patch("core.pipeline_live_pro._decision_log"),
                patch("core.api.log_blocked_execution") as blocked_log,
            ):
                result = pipeline.process(raw)
                await self._allow_dispatch_task_to_finish(dispatched_tasks)

        self.assertEqual(result, signal)
        self.assertEqual(api.last_signal, signal)

        api._send_to_ninjatrader.assert_not_awaited()
        api._send_to_telegram.assert_not_awaited()

        pipeline.exit_engine.open_from_signal.assert_not_called()
        pipeline.dedup.is_duplicate.assert_called_once_with(signal)
        pipeline._log_signal.assert_called_once_with(signal)

        blocked_log.assert_called_once()
        decision = blocked_log.call_args.args[0]
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "enable_trading_disabled")


if __name__ == "__main__":
    unittest.main()
