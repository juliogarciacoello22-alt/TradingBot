import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.pipeline_live_pro import PipelineLivePRO


class PipelineBlockedDispatchNoInternalTradeTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_blocked_dispatch_must_not_open_internal_trade(self):
        api = Mock()
        api.loader = Mock()
        api.prev_delta = None
        api.send_signal = AsyncMock(
            return_value={
                "allowed": False,
                "run_mode": "PLAYBACK",
                "account": "playback",
                "reason": "enable_trading_disabled",
                "enable_trading": False,
            }
        )

        pipeline = PipelineLivePRO(api, is_live=True)
        pipeline.exit_engine = Mock()
        pipeline.exit_engine.open_from_signal = Mock()

        signal = {
            "side": "BUY",
            "entry": 100.0,
            "stop": 99.0,
            "tp1": 101.0,
        }

        on_allowed = Mock()

        dispatch_task = pipeline._dispatch_signal(
            signal,
            on_allowed=on_allowed,
        )

        if isinstance(dispatch_task, asyncio.Task):
            result = await dispatch_task
        else:
            result = dispatch_task

        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "enable_trading_disabled")
        on_allowed.assert_not_called()
        pipeline.exit_engine.open_from_signal.assert_not_called()

    async def test_process_must_not_open_internal_trade_when_dispatch_is_blocked(
        self,
    ):
        api = Mock()
        api.loader = Mock()
        api.prev_delta = None

        candle = SimpleNamespace(
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=1000,
            timestamp="2026-07-10T12:00:00Z",
        )

        api.loader.load.return_value = {
            "1m": [candle],
            "5m": [candle, candle, candle],
            "30m": [candle],
        }

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
        pipeline.timing_engine.build_timing.return_value = {"valid": True}

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

        blocked_result = {
            "allowed": False,
            "run_mode": "PLAYBACK",
            "account": "playback",
            "reason": "enable_trading_disabled",
            "enable_trading": False,
        }

        def blocked_dispatch(signal, on_allowed=None):
            return blocked_result

        pipeline._dispatch_signal = Mock(side_effect=blocked_dispatch)

        raw = {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000,
            "timestamp": "2026-07-10T12:00:00Z",
        }

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

        self.assertEqual(result, signal)
        pipeline._dispatch_signal.assert_called_once()

        dispatch_args, dispatch_kwargs = pipeline._dispatch_signal.call_args
        self.assertEqual(dispatch_args[0], signal)
        self.assertIn("on_allowed", dispatch_kwargs)

        pipeline.exit_engine.open_from_signal.assert_not_called()


if __name__ == "__main__":
    unittest.main()