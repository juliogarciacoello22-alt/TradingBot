import unittest

from core.observational_structural_recovery import evaluate_observational_structural_recovery


def _base_ctx() -> dict:
    return {
        "displacement_real": None,
        "displacement_reason_real": "body_too_small",
        "body_ratio": 0.52,
        "range_expansion": 2.1,
        "close_location": 0.80,
        "delta": 10,
        "side_esperado": "BUY",
        "shadow_direction": "up",
        "shadow_ob_internal_v2_candidate": True,
    }


class ObservationalStructuralRecoveryTests(unittest.TestCase):
    def test_accepts_buy_candidate_with_high_confidence(self):
        result = evaluate_observational_structural_recovery(_base_ctx())
        self.assertTrue(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "accepted_observational_structural_recovery",
        )
        self.assertEqual(result["observational_structural_recovery_direction"], "up")
        self.assertEqual(result["observational_structural_recovery_body_ratio_band"], "0.50_0.55")
        self.assertEqual(result["observational_structural_recovery_side_alignment"], "aligned")
        self.assertEqual(result["observational_structural_recovery_confidence"], "HIGH")

    def test_accepts_sell_candidate_with_medium_confidence(self):
        ctx = _base_ctx() | {
            "body_ratio": 0.47,
            "range_expansion": 1.4,
            "close_location": 0.20,
            "delta": -10,
            "side_esperado": "SELL",
            "shadow_direction": "down",
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertTrue(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "accepted_observational_structural_recovery",
        )
        self.assertEqual(result["observational_structural_recovery_direction"], "down")
        self.assertEqual(result["observational_structural_recovery_body_ratio_band"], "0.45_0.50")
        self.assertEqual(result["observational_structural_recovery_side_alignment"], "aligned")
        self.assertEqual(result["observational_structural_recovery_confidence"], "MEDIUM")

    def test_rejects_when_real_displacement_is_present(self):
        ctx = _base_ctx() | {"displacement_real": "up"}
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_real_displacement_present",
        )

    def test_rejects_when_reason_is_not_body_too_small(self):
        ctx = _base_ctx() | {"displacement_reason_real": "delta_not_confirming_up"}
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_reason_not_body_too_small",
        )

    def test_rejects_when_body_ratio_is_below_band(self):
        ctx = _base_ctx() | {"body_ratio": 0.44}
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_body_ratio_out_of_band",
        )
        self.assertEqual(result["observational_structural_recovery_body_ratio_band"], "below_045")

    def test_rejects_when_body_ratio_is_above_or_equal_high_band(self):
        ctx = _base_ctx() | {"body_ratio": 0.55}
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_body_ratio_out_of_band",
        )
        self.assertEqual(result["observational_structural_recovery_body_ratio_band"], "ge_055")

    def test_rejects_when_range_expansion_is_weak(self):
        ctx = _base_ctx() | {"range_expansion": 1.19}
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_range_expansion_weak",
        )

    def test_rejects_buy_when_close_location_is_not_directional(self):
        ctx = _base_ctx() | {"close_location": 0.64}
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_close_location_not_directional",
        )

    def test_rejects_sell_when_close_location_is_not_directional(self):
        ctx = _base_ctx() | {
            "side_esperado": "SELL",
            "shadow_direction": "down",
            "close_location": 0.36,
            "delta": -10,
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_close_location_not_directional",
        )

    def test_rejects_buy_when_delta_does_not_confirm(self):
        ctx = _base_ctx() | {"delta": 0}
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_delta_not_confirming",
        )

    def test_rejects_sell_when_delta_does_not_confirm(self):
        ctx = _base_ctx() | {
            "side_esperado": "SELL",
            "shadow_direction": "down",
            "close_location": 0.20,
            "delta": 0,
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_delta_not_confirming",
        )

    def test_rejects_when_shadow_ob_candidate_is_missing(self):
        ctx = _base_ctx() | {"shadow_ob_internal_v2_candidate": False}
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_no_shadow_ob_internal_candidate",
        )

    def test_rejects_when_shadow_direction_mismatches_expected_direction(self):
        ctx = _base_ctx() | {
            "body_ratio": 0.47,
            "range_expansion": 1.36,
            "close_location": 0.30,
            "delta": -1,
            "side_esperado": "SELL",
            "shadow_direction": "up",
            "shadow_ob_internal_v2_candidate": True,
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_shadow_direction_mismatch",
        )
        self.assertEqual(result["observational_structural_recovery_direction"], "up")
        self.assertEqual(result["observational_structural_recovery_side_alignment"], "mismatch")
        self.assertEqual(result["observational_structural_recovery_confidence"], "LOW")

    def test_timestamp_1782490860_expected_positive(self):
        ctx = _base_ctx() | {
            "body_ratio": 0.4595588235,
            "range_expansion": 3.0561797753,
            "close_location": 0.3492647059,
            "delta": -717.3713235294,
            "side_esperado": "SELL",
            "shadow_direction": "down",
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertTrue(result["observational_structural_recovery"])
        self.assertEqual(result["observational_structural_recovery_reason"], "accepted_observational_structural_recovery")
        self.assertEqual(result["observational_structural_recovery_direction"], "down")
        self.assertEqual(result["observational_structural_recovery_body_ratio_band"], "0.45_0.50")

    def test_timestamp_1782496140_expected_positive(self):
        ctx = _base_ctx() | {
            "body_ratio": 0.5081967213,
            "range_expansion": 2.2592592593,
            "close_location": 0.0327868852,
            "delta": -248.5081967213,
            "side_esperado": "SELL",
            "shadow_direction": "down",
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertTrue(result["observational_structural_recovery"])
        self.assertEqual(result["observational_structural_recovery_reason"], "accepted_observational_structural_recovery")
        self.assertEqual(result["observational_structural_recovery_direction"], "down")
        self.assertEqual(result["observational_structural_recovery_body_ratio_band"], "0.50_0.55")

    def test_timestamp_1782496440_expected_positive(self):
        ctx = _base_ctx() | {
            "body_ratio": 0.4933333333,
            "range_expansion": 1.5625,
            "close_location": 0.1066666667,
            "delta": -157.8666666667,
            "side_esperado": "SELL",
            "shadow_direction": "down",
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertTrue(result["observational_structural_recovery"])
        self.assertEqual(result["observational_structural_recovery_reason"], "accepted_observational_structural_recovery")
        self.assertEqual(result["observational_structural_recovery_direction"], "down")
        self.assertEqual(result["observational_structural_recovery_body_ratio_band"], "0.45_0.50")

    def test_timestamp_1782497700_expected_mismatch_rejection(self):
        ctx = _base_ctx() | {
            "body_ratio": 0.4705882353,
            "range_expansion": 1.36,
            "close_location": 0.20,
            "delta": -1,
            "side_esperado": "SELL",
            "shadow_direction": "up",
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(result["observational_structural_recovery_reason"], "rejected_shadow_direction_mismatch")
        self.assertEqual(result["observational_structural_recovery_direction"], "up")

    def test_timestamp_1782489000_expected_no_shadow_ob_candidate(self):
        ctx = _base_ctx() | {
            "body_ratio": 0.4950495050,
            "range_expansion": 1.6031746032,
            "close_location": 0.0,
            "delta": -363.3663366337,
            "side_esperado": "SELL",
            "shadow_direction": "down",
            "shadow_ob_internal_v2_candidate": False,
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_no_shadow_ob_internal_candidate",
        )

    def test_timestamp_1782491220_expected_no_shadow_ob_candidate(self):
        ctx = _base_ctx() | {
            "body_ratio": 0.5395683453,
            "range_expansion": 1.7820512821,
            "close_location": 0.8057553957,
            "delta": 350.7194244604,
            "side_esperado": "BUY",
            "shadow_direction": "up",
            "shadow_ob_internal_v2_candidate": False,
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(
            result["observational_structural_recovery_reason"],
            "rejected_no_shadow_ob_internal_candidate",
        )

    def test_missing_shadow_direction_uses_none(self):
        ctx = _base_ctx() | {
            "body_ratio": 0.47,
            "range_expansion": 1.36,
            "close_location": 0.20,
            "delta": -1,
            "side_esperado": "SELL",
            "shadow_direction": None,
        }
        result = evaluate_observational_structural_recovery(ctx)
        self.assertFalse(result["observational_structural_recovery"])
        self.assertEqual(result["observational_structural_recovery_direction"], "none")
        self.assertEqual(result["observational_structural_recovery_reason"], "rejected_shadow_direction_mismatch")


if __name__ == "__main__":
    unittest.main()
