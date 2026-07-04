from __future__ import annotations

"""
Observational-only evaluator for structural recovery research.

This module is intentionally isolated from the real trading contract. The
returned payload is diagnostic only and must not be interpreted as a signal,
missed trade, or authorization to affect risk, execution, dispatch, or runtime.
"""

from typing import Any, Mapping


BODY_RATIO_LOW = 0.45
BODY_RATIO_HIGH = 0.55
RANGE_EXPANSION_MIN = 1.20
BUY_CLOSE_LOCATION_MIN = 0.65
SELL_CLOSE_LOCATION_MAX = 0.35
BUY_CLOSE_LOCATION_HIGH = 0.75
SELL_CLOSE_LOCATION_HIGH = 0.25

REASON_ACCEPTED = "accepted_observational_structural_recovery"
REASON_REAL_DISPLACEMENT_PRESENT = "rejected_real_displacement_present"
REASON_NOT_BODY_TOO_SMALL = "rejected_reason_not_body_too_small"
REASON_BODY_RATIO_OUT_OF_BAND = "rejected_body_ratio_out_of_band"
REASON_RANGE_EXPANSION_WEAK = "rejected_range_expansion_weak"
REASON_CLOSE_LOCATION_NOT_DIRECTIONAL = "rejected_close_location_not_directional"
REASON_DELTA_NOT_CONFIRMING = "rejected_delta_not_confirming"
REASON_NO_SHADOW_OB_INTERNAL_CANDIDATE = "rejected_no_shadow_ob_internal_candidate"
REASON_SHADOW_DIRECTION_MISMATCH = "rejected_shadow_direction_mismatch"

DIRECTION_NONE = "none"
ALIGNMENT_ALIGNED = "aligned"
ALIGNMENT_MISMATCH = "mismatch"
ALIGNMENT_MISSING = "missing"

CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_HIGH = "HIGH"

BODY_BAND_BELOW = "below_045"
BODY_BAND_MID_LOW = "0.45_0.50"
BODY_BAND_MID_HIGH = "0.50_0.55"
BODY_BAND_HIGH = "ge_055"


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _body_ratio_band(body_ratio: Any) -> str | None:
    value = _to_float(body_ratio)
    if value is None:
        return None
    if value < BODY_RATIO_LOW:
        return BODY_BAND_BELOW
    if value < 0.50:
        return BODY_BAND_MID_LOW
    if value < BODY_RATIO_HIGH:
        return BODY_BAND_MID_HIGH
    return BODY_BAND_HIGH


def _base_output(ctx: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "observational_structural_recovery": False,
        "observational_structural_recovery_reason": REASON_NOT_BODY_TOO_SMALL,
        "observational_structural_recovery_direction": DIRECTION_NONE,
        "observational_structural_recovery_body_ratio": ctx.get("body_ratio"),
        "observational_structural_recovery_body_ratio_band": _body_ratio_band(ctx.get("body_ratio")),
        "observational_structural_recovery_range_expansion": ctx.get("range_expansion"),
        "observational_structural_recovery_close_location": ctx.get("close_location"),
        "observational_structural_recovery_delta": ctx.get("delta"),
        "observational_structural_recovery_shadow_ob_candidate": ctx.get("shadow_ob_internal_v2_candidate"),
        "observational_structural_recovery_side_alignment": ALIGNMENT_MISSING,
        "observational_structural_recovery_confidence": CONFIDENCE_LOW,
    }


def evaluate_observational_structural_recovery(ctx: Mapping[str, Any]) -> dict[str, Any]:
    """
    Evaluate whether a failed real displacement shows enough structural evidence
    to be logged as an observational-only recovery candidate.

    This function is pure and has no side effects. It never writes into the real
    contract or into shadow-proxy outputs.
    """
    out = _base_output(ctx)

    if ctx.get("displacement_real") is not None:
        out["observational_structural_recovery_reason"] = REASON_REAL_DISPLACEMENT_PRESENT
        return out

    if ctx.get("displacement_reason_real") != "body_too_small":
        out["observational_structural_recovery_reason"] = REASON_NOT_BODY_TOO_SMALL
        return out

    body_ratio = _to_float(ctx.get("body_ratio"))
    if body_ratio is None or not (BODY_RATIO_LOW <= body_ratio < BODY_RATIO_HIGH):
        out["observational_structural_recovery_reason"] = REASON_BODY_RATIO_OUT_OF_BAND
        return out

    range_expansion = _to_float(ctx.get("range_expansion"))
    if range_expansion is None or range_expansion < RANGE_EXPANSION_MIN:
        out["observational_structural_recovery_reason"] = REASON_RANGE_EXPANSION_WEAK
        return out

    side_esperado = ctx.get("side_esperado")
    close_location = _to_float(ctx.get("close_location"))
    delta = _to_float(ctx.get("delta"))

    if side_esperado == "BUY":
        expected_direction = "up"
        if close_location is None or close_location < BUY_CLOSE_LOCATION_MIN:
            out["observational_structural_recovery_reason"] = REASON_CLOSE_LOCATION_NOT_DIRECTIONAL
            return out
        if delta is None or delta <= 0:
            out["observational_structural_recovery_reason"] = REASON_DELTA_NOT_CONFIRMING
            return out
    elif side_esperado == "SELL":
        expected_direction = "down"
        if close_location is None or close_location > SELL_CLOSE_LOCATION_MAX:
            out["observational_structural_recovery_reason"] = REASON_CLOSE_LOCATION_NOT_DIRECTIONAL
            return out
        if delta is None or delta >= 0:
            out["observational_structural_recovery_reason"] = REASON_DELTA_NOT_CONFIRMING
            return out
    else:
        out["observational_structural_recovery_reason"] = REASON_CLOSE_LOCATION_NOT_DIRECTIONAL
        return out

    if ctx.get("shadow_ob_internal_v2_candidate") is not True:
        out["observational_structural_recovery_reason"] = REASON_NO_SHADOW_OB_INTERNAL_CANDIDATE
        return out

    shadow_direction = ctx.get("shadow_direction") or DIRECTION_NONE
    out["observational_structural_recovery_direction"] = shadow_direction

    if shadow_direction != expected_direction:
        out["observational_structural_recovery_side_alignment"] = ALIGNMENT_MISMATCH
        out["observational_structural_recovery_reason"] = REASON_SHADOW_DIRECTION_MISMATCH
        return out

    out["observational_structural_recovery"] = True
    out["observational_structural_recovery_reason"] = REASON_ACCEPTED
    out["observational_structural_recovery_side_alignment"] = ALIGNMENT_ALIGNED

    if body_ratio >= 0.50 and range_expansion >= 2.00:
        close_is_high = (
            close_location >= BUY_CLOSE_LOCATION_HIGH
            if side_esperado == "BUY"
            else close_location <= SELL_CLOSE_LOCATION_HIGH
        )
        if close_is_high:
            out["observational_structural_recovery_confidence"] = CONFIDENCE_HIGH
            return out

    out["observational_structural_recovery_confidence"] = CONFIDENCE_MEDIUM
    return out


__all__ = ["evaluate_observational_structural_recovery"]
