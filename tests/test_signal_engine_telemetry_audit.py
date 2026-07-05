
import unittest

from core.signal_engine_v4_pro import SignalEngineV4


class _DummyReaction:
    def detect_reaction(self, *args, **kwargs):
        return None


class SignalEngineTelemetryAuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = SignalEngineV4(_DummyReaction())

    def test_valid_entry_behavior_is_unchanged_when_mitigation_light_is_true(self):
        micro = {
            "displacement": "up",
            "momentum": "up",
            "fake_displacement": False,
            "inducement": None,
            "mitigation_light": True,
            "mitigation_contamination": False,
            "mitigation_light_v2": False,
            "mitigation_contamination_reason": "overlap_only",
        }

        result = self.engine._valid_entry(micro)

        self.assertFalse(result)
        self.assertEqual(self.engine.last_valid_entry_reason, "mitigation_light_true")
        self.assertIsInstance(self.engine.last_valid_entry_shadow, dict)
        self.assertTrue(self.engine.last_valid_entry_shadow["valid_entry_ab_shadow_would_unlock"])
        self.assertIn("valid_entry_ab_delta", micro)

    def test_valid_entry_pass_still_passes_and_shadow_is_populated(self):
        micro = {
            "displacement": "up",
            "momentum": "up",
            "fake_displacement": False,
            "inducement": None,
            "mitigation_light": False,
            "mitigation_contamination": False,
            "mitigation_light_v2": False,
        }

        result = self.engine._valid_entry(micro)

        self.assertTrue(result)
        self.assertEqual(self.engine.last_valid_entry_reason, "entry_filters_passed")
        self.assertIsInstance(self.engine.last_valid_entry_shadow, dict)
        self.assertIsNone(self.engine.last_valid_entry_shadow["valid_entry_ab_delta"])


if __name__ == "__main__":
    unittest.main()
