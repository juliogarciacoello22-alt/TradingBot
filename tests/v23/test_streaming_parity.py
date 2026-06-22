import unittest
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from core.strategy_v23.config import StrategyConfigV23
from core.strategy_v23.models import Bar
from core.strategy_v23.streaming_adapter import StrategyStreamV23


class StreamingParityTests(unittest.TestCase):
    def test_offline_bars_and_live_payloads_have_identical_decisions(self):
        config = StrategyConfigV23()
        offline = StrategyStreamV23(config)
        live = StrategyStreamV23(config)
        start = datetime(2025, 11, 4, 0, 0, tzinfo=ZoneInfo("America/Chicago"))
        bars = []
        price = 25000.0
        for index in range(600):
            wave = math.sin(index / 17) * 2
            bars.append(Bar(
                start + timedelta(minutes=index),
                price + wave,
                price + wave + 2,
                price + wave - 2,
                price + wave + math.sin(index / 5),
                100 + (index % 37) * 3,
            ))
            price += math.sin(index / 31) * 0.25

        offline_decisions = []
        live_decisions = []
        for candle in bars:
            offline_decisions.append(offline.process_closed_bar(candle))
            live_decisions.append(live.process_live_payload({
                "timestamp": candle.timestamp.timestamp(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "barType": "Minute",
                "barSize": 1,
                "isClosed": True,
            }))

        self.assertEqual(offline_decisions, live_decisions)
        self.assertGreater(sum(decision is not None for decision in offline_decisions), 0)
        self.assertEqual(offline.rejections, live.rejections)
        self.assertEqual(offline.core.levels.levels, live.core.levels.levels)
        self.assertEqual(offline.core.levels.dynamic, live.core.levels.dynamic)

    def test_open_live_bar_is_ignored_without_state_change(self):
        stream = StrategyStreamV23()
        result = stream.process_live_payload({"isClosed": False})
        self.assertIsNone(result)
        self.assertEqual(stream.core.bars, [])


if __name__ == "__main__":
    unittest.main()
