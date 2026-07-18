from dataclasses import FrozenInstanceError

import pytest

from core.domain.security_policy import SecurityDecisionCode
from core.runtime_guard import ExecutionAuthorization
from core.runtime_security_adapter import evaluate_shadow_security
from core.security_context_provider import (
    ProviderFailure,
    ProviderFailureCode,
    SecurityContextProviderResult,
)
from tests.test_security_context_domain import MONOTONIC_NOW_NS, NOW, make_valid_snapshot
from tests.test_security_policy_matrix import freshness, high_water


def evaluate(legacy, result):
    return evaluate_shadow_security(
        legacy,
        result,
        evaluated_at_utc=NOW,
        monotonic_observation_ns=MONOTONIC_NOW_NS,
        freshness_policy=freshness(),
        high_water_marks=high_water(),
    )


@pytest.mark.parametrize("legacy_allowed", (False, True))
def test_adapter_preserves_same_legacy_instance_allowed_and_reason(legacy_allowed):
    legacy = ExecutionAuthorization(
        legacy_allowed,
        "PAPER",
        "Sim101",
        "legacy-reason",
        True,
    )
    before = legacy.to_dict()
    evaluation = evaluate(legacy, SecurityContextProviderResult.success(make_valid_snapshot()))
    assert evaluation.legacy_decision is legacy
    assert legacy.to_dict() == before
    assert evaluation.operational_allowed is legacy.allowed
    assert evaluation.audit_payload.legacy_reason == legacy.reason


def test_frozen_shadow_formula_for_legacy_allowed_and_security_pass():
    legacy = ExecutionAuthorization(True, "PAPER", "Sim101", "allowed", True)
    evaluation = evaluate(legacy, SecurityContextProviderResult.success(make_valid_snapshot()))
    assert evaluation.security_decision.code is SecurityDecisionCode.SHADOW_PASS
    assert evaluation.operational_allowed is True
    assert evaluation.shadow_would_allow is True
    with pytest.raises(FrozenInstanceError):
        evaluation.operational_allowed = False


def test_legacy_blocked_never_becomes_shadow_allowed_even_when_security_passes():
    legacy = ExecutionAuthorization(False, "PAPER", "Sim101", "legacy-block", True)
    evaluation = evaluate(legacy, SecurityContextProviderResult.success(make_valid_snapshot()))
    assert evaluation.security_decision.code is SecurityDecisionCode.SHADOW_PASS
    assert evaluation.operational_allowed is False
    assert evaluation.shadow_would_allow is False


@pytest.mark.parametrize(
    ("failure_code", "security_code"),
    (
        (ProviderFailureCode.TIMEOUT, SecurityDecisionCode.PROVIDER_FAILURE),
        (ProviderFailureCode.UNAVAILABLE, SecurityDecisionCode.PROVIDER_FAILURE),
        (
            ProviderFailureCode.PARTIAL_SNAPSHOT,
            SecurityDecisionCode.CONTEXT_INCOMPLETE,
        ),
        (
            ProviderFailureCode.UNSUPPORTED_VERSION,
            SecurityDecisionCode.CONTEXT_VERSION_UNSUPPORTED,
        ),
        (ProviderFailureCode.HASH_MISMATCH, SecurityDecisionCode.EVIDENCE_CONFLICT),
    ),
)
def test_provider_failure_never_verifies_context_or_expands_permissions(
    failure_code,
    security_code,
):
    legacy = ExecutionAuthorization(True, "PAPER", "Sim101", "allowed", True)
    result = SecurityContextProviderResult.failed(
        ProviderFailure(failure_code, "safe-failure", True)
    )
    evaluation = evaluate(legacy, result)
    assert evaluation.legacy_decision is legacy
    assert evaluation.operational_allowed is True
    assert evaluation.shadow_would_allow is False
    assert evaluation.security_decision.context_verified is False
    assert evaluation.security_decision.code is security_code


def test_audit_payload_contains_only_frozen_sanitized_fields():
    legacy = ExecutionAuthorization(True, "PAPER", "Sim101", "allowed", True)
    payload = evaluate(
        legacy,
        SecurityContextProviderResult.success(make_valid_snapshot()),
    ).audit_payload.to_dict()
    assert set(payload) == {
        "policy_version",
        "context_id",
        "context_hash",
        "context_generation",
        "legacy_allowed",
        "legacy_reason",
        "shadow_would_allow",
        "primary_security_code",
        "secondary_security_codes",
        "evidence_hashes",
        "source_id",
        "boot_id",
        "evaluated_at_utc",
    }
    serialized_names = " ".join(payload).lower()
    assert all(word not in serialized_names for word in ("signature", "secret", "bearer", "certificate"))
