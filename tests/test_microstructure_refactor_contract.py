
import unittest

from core.microstructure_engine import MicrostructureEngine


class _Candle:
    def __init__(self, open_, high, low, close):
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.body = abs(close - open_)
        self.range = high - low


class MicrostructureRefactorContractTests(unittest.TestCase):
    def setUp(self):
        self.engine = MicrostructureEngine()

    def test_mitigation_light_diagnostics_preserve_overlap_reasoning(self):
        current = _Candle(10, 20, 5, 15)
        previous = _Candle(9, 16, 8, 12)

        diagnostics = self.engine._mitigation_light_diagnostics(current, previous)

        self.assertTrue(diagnostics["value"])
        self.assertEqual(diagnostics["reason"], "both_close_overlaps")

    def test_mitigation_light_v2_shadow_preserves_counter_sweep_block(self):
        shadow = self.engine._mitigation_light_v2_shadow(
            mitigation_overlap=True,
            mitigation_overlap_reason="both_close_overlaps",
            disp="up",
            momentum="up",
            sweep="up",
            absorption=None,
            breaker=None,
            fake_displacement=False,
            delta=10,
        )

        self.assertTrue(shadow["mitigation_contamination"])
        self.assertEqual(shadow["mitigation_contamination_reason"], "counter_sweep")
        self.assertTrue(shadow["mitigation_light_v2"])


if __name__ == "__main__":
    unittest.main()
