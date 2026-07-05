
import unittest

from core.pipeline_live_pro import _build_full_path_snapshot


class _Candle:
    def __init__(self):
        self.timestamp = 1234567890
        self.close = 101.25


class _SignalEngine:
    last_valid_entry_reason = "entry_filters_passed"
    last_build_signal_reason = "scalper_generated"
    last_valid_entry_shadow = {"valid_entry_ab_delta": "shadow_would_unlock"}


class PipelineFullPathSnapshotBuilderTests(unittest.TestCase):
    def test_build_full_path_snapshot_is_pure_and_preserves_missing_fields_contract(self):
        snapshot = _build_full_path_snapshot(
            session_id="session-1",
            raw={"timestamp": 1234567890},
            candle=_Candle(),
            tf={"1m": [_Candle()]},
            micro_for_valid_entry={"mitigation_light_reason": "no_close_overlap", "ob": {}},
            timing={"enabled": True},
            delta=10.0,
            context={"bias": "bullish"},
            forecast={"target": 1},
            signal_engine=_SignalEngine(),
            signal={"side": "BUY"},
        )

        self.assertEqual(snapshot["decision_id"], "session-1|1234567890")
        self.assertEqual(snapshot["price"], 101.25)
        self.assertEqual(
            snapshot["stage_outputs"]["signal_engine"]["last_valid_entry_reason"],
            "entry_filters_passed",
        )
        self.assertEqual(snapshot["missing_fields"], [])


if __name__ == "__main__":
    unittest.main()
