from dataclasses import FrozenInstanceError

import pytest

from core.domain.runtime_policy import (
    SafetyPolicyDecision,
    SignalPolicyDecision,
    account_is_safe_non_real,
    decide_runtime_safety,
    decide_signal_permission,
)


ALLOWED = {"PLAYBACK", "PAPER", "PAPER_LIVE", "LIVE"}
MARKERS = ("playback", "replay", "sim", "paper")


def _safety(**overrides):
    values = {
        "run_mode": "PLAYBACK",
        "trading_enabled": False,
        "enable_valid": True,
        "account": None,
        "live_trading_approved": False,
        "approval_valid": True,
        "allowed_run_modes": ALLOWED,
        "safe_account_markers": MARKERS,
    }
    values.update(overrides)
    return decide_runtime_safety(**values)


def test_account_classification_is_deterministic_and_legacy_compatible():
    assert account_is_safe_non_real("Market Replay 01", MARKERS) is True
    assert account_is_safe_non_real("Sim101", MARKERS) is True
    assert account_is_safe_non_real("Paper-Demo", MARKERS) is True
    assert account_is_safe_non_real("REAL-01", MARKERS) is False
    assert account_is_safe_non_real(None, MARKERS) is False


def test_runtime_policy_preserves_fail_closed_precedence():
    invalid = _safety(
        run_mode="INVALID",
        enable_valid=False,
        approval_valid=False,
    )
    malformed_enable = _safety(enable_valid=False, approval_valid=False)
    malformed_approval = _safety(approval_valid=False)

    assert invalid.reason == "invalid_run_mode"
    assert malformed_enable.reason == "malformed_enable_trading"
    assert malformed_approval.reason == "malformed_live_trading_approved"
    assert not invalid.startup_allowed
    assert not malformed_enable.startup_allowed
    assert not malformed_approval.startup_allowed


def test_policy_results_are_frozen_internal_values():
    safety = _safety()
    permission = decide_signal_permission(
        run_mode=safety.run_mode,
        startup_allowed=safety.startup_allowed,
        trading_enabled=safety.trading_enabled,
        account=safety.account,
        live_allowed=safety.live_allowed,
        safety_reason=safety.reason,
        allowed_run_modes=ALLOWED,
        safe_account_markers=MARKERS,
    )

    assert isinstance(safety, SafetyPolicyDecision)
    assert isinstance(permission, SignalPolicyDecision)
    with pytest.raises(FrozenInstanceError):
        safety.reason = "changed"
    with pytest.raises(FrozenInstanceError):
        permission.reason = "changed"


def test_policy_has_no_hidden_state_between_equal_calls():
    first = _safety(
        run_mode="LIVE",
        trading_enabled=True,
        account="REAL-01",
        live_trading_approved=True,
    )
    second = _safety(
        run_mode="LIVE",
        trading_enabled=True,
        account="REAL-01",
        live_trading_approved=True,
    )

    assert first == second
    assert first.reason == "live_trading_approved"
    assert first.live_allowed is True
