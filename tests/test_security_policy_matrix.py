from dataclasses import fields, replace
from datetime import timedelta

import pytest

from core.domain.identifiers import BootId, FencingToken, RecoveryId, SourceId
from core.domain.security import AuthenticationState, LeaseState
from core.domain.security_context import (
    ClockConfidence,
    EvidenceVerificationState,
    RecoveryActivity,
    RecoveryEvidence,
    VerificationEnvelope,
)
from core.domain.security_policy import (
    SecurityDecisionCode,
    SecurityFreshnessPolicy,
    SecurityGateName,
    SecurityHighWaterMarks,
    SecurityPolicyDecision,
    evaluate_security_context,
)
from tests.test_security_context_domain import (
    MONOTONIC_NOW_NS,
    NOW,
    make_lock,
    make_valid_snapshot,
    verified_envelope,
)


EXPECTED_CODES = (
    "SECURITY.CONTEXT_MISSING",
    "SECURITY.CONTEXT_INCOMPLETE",
    "SECURITY.CONTEXT_UNVERIFIED",
    "SECURITY.CONTEXT_VERSION_UNSUPPORTED",
    "SECURITY.CONTEXT_GENERATION_ROLLBACK",
    "SECURITY.CLOCK_UNTRUSTED",
    "SECURITY.SOURCE_UNAUTHORIZED",
    "SECURITY.BOOT_MISMATCH",
    "SECURITY.AUTHORITY_MISSING",
    "SECURITY.AUTHORITY_UNVERIFIED",
    "SECURITY.AUTHORITY_EXPIRED",
    "SECURITY.AUTHENTICATION_INVALID",
    "SECURITY.HEARTBEAT_MISSING",
    "SECURITY.HEARTBEAT_STALE",
    "SECURITY.LEASE_MISSING",
    "SECURITY.LEASE_NOT_ACTIVE",
    "SECURITY.LEASE_EXPIRED",
    "SECURITY.LEASE_REVOKED",
    "SECURITY.FENCING_MISMATCH",
    "SECURITY.LOCK_ACTIVE",
    "SECURITY.MULTIPLE_LOCKS_ACTIVE",
    "SECURITY.EVIDENCE_CONFLICT",
    "SECURITY.RECOVERY_ACTIVE",
    "SECURITY.PROVIDER_FAILURE",
    "SECURITY.SHADOW_PASS",
)

EXPECTED_GATES = (
    "CONTEXT_AVAILABILITY",
    "SCHEMA_VERSION",
    "CONTEXT_INTEGRITY",
    "CONTEXT_VERIFICATION",
    "CONTEXT_GENERATION",
    "EVIDENCE_CONSISTENCY",
    "CLOCK",
    "SOURCE",
    "BOOT",
    "AUTHORITY",
    "AUTHENTICATION",
    "REVOCATION",
    "LEASE",
    "FENCING",
    "HEARTBEAT",
    "LOCKS",
    "RECOVERY",
    "SHADOW_RESULT",
)


def freshness() -> SecurityFreshnessPolicy:
    return SecurityFreshnessPolicy(
        heartbeat_max_age=timedelta(seconds=30),
        authority_max_age=timedelta(minutes=5),
        authentication_max_age=timedelta(minutes=5),
        revocation_max_age=timedelta(minutes=5),
        allowed_clock_skew=timedelta(milliseconds=10),
        lease_expiry_margin=timedelta(0),
    )


def high_water(**overrides) -> SecurityHighWaterMarks:
    values = {
        "expected_source_id": SourceId("source-1"),
        "authorized_source_ids": (SourceId("source-1"),),
        "expected_boot_id": BootId("boot-1"),
        "minimum_context_generation": 4,
        "minimum_heartbeat_sequence": 12,
        "expected_fencing_token": FencingToken(7),
        "minimum_fencing_token": FencingToken(7),
        "minimum_revocation_generation": 3,
    }
    values.update(overrides)
    return SecurityHighWaterMarks(**values)


def evaluate(snapshot=None, *, marks=None, context_failure=None):
    return evaluate_security_context(
        make_valid_snapshot() if snapshot is None and context_failure is None else snapshot,
        context_failure=context_failure,
        evaluated_at_utc=NOW,
        monotonic_observation_ns=MONOTONIC_NOW_NS,
        freshness_policy=freshness(),
        high_water_marks=marks or high_water(),
    )


def test_security_code_list_is_frozen_at_exactly_twenty_five_codes():
    assert tuple(item.value for item in SecurityDecisionCode) == EXPECTED_CODES
    assert len(SecurityDecisionCode) == 25


def test_gate_order_is_frozen_at_exactly_eighteen_gates():
    assert tuple(item.value for item in SecurityGateName) == EXPECTED_GATES
    assert len(SecurityGateName) == 18


def test_policy_decision_has_no_operational_authorization_fields():
    names = {item.name for item in fields(SecurityPolicyDecision)}
    assert "allowed" not in names
    assert "authorized" not in names


def test_valid_context_produces_only_shadow_pass():
    decision = evaluate()
    assert decision.context_verified is True
    assert decision.all_security_gates_passed is True
    assert decision.code is SecurityDecisionCode.SHADOW_PASS
    assert decision.secondary_codes == ()


@pytest.mark.parametrize(
    ("snapshot_factory", "marks", "expected"),
    (
        (
            lambda: replace(
                make_valid_snapshot(),
                overall_verification=EvidenceVerificationState.UNKNOWN,
            ),
            high_water(),
            SecurityDecisionCode.CONTEXT_UNVERIFIED,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                overall_verification=EvidenceVerificationState.REJECTED,
            ),
            high_water(),
            SecurityDecisionCode.EVIDENCE_CONFLICT,
        ),
        (
            make_valid_snapshot,
            high_water(minimum_context_generation=5),
            SecurityDecisionCode.CONTEXT_GENERATION_ROLLBACK,
        ),
        (
            make_valid_snapshot,
            high_water(expected_source_id=SourceId("source-2")),
            SecurityDecisionCode.SOURCE_UNAUTHORIZED,
        ),
        (
            make_valid_snapshot,
            high_water(expected_boot_id=BootId("boot-2")),
            SecurityDecisionCode.BOOT_MISMATCH,
        ),
        (
            lambda: replace(make_valid_snapshot(), authority_assertion=None),
            high_water(),
            SecurityDecisionCode.AUTHORITY_MISSING,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                authority_assertion=replace(
                    make_valid_snapshot().authority_assertion,
                    verified=False,
                ),
            ),
            high_water(),
            SecurityDecisionCode.AUTHORITY_UNVERIFIED,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                authority_assertion=replace(
                    make_valid_snapshot().authority_assertion,
                    asserted_at=NOW - timedelta(minutes=6),
                ),
            ),
            high_water(),
            SecurityDecisionCode.AUTHORITY_EXPIRED,
        ),
        (
            lambda: replace(make_valid_snapshot(), authentication=None),
            high_water(),
            SecurityDecisionCode.AUTHENTICATION_INVALID,
        ),
        (
            lambda: replace(make_valid_snapshot(), heartbeat=None),
            high_water(),
            SecurityDecisionCode.HEARTBEAT_MISSING,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                heartbeat=replace(
                    make_valid_snapshot().heartbeat,
                    observed_at=NOW - timedelta(minutes=1),
                ),
            ),
            high_water(),
            SecurityDecisionCode.HEARTBEAT_STALE,
        ),
        (
            lambda: replace(make_valid_snapshot(), lease=None),
            high_water(),
            SecurityDecisionCode.LEASE_MISSING,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                lease=replace(make_valid_snapshot().lease, state=LeaseState.ISSUED),
            ),
            high_water(),
            SecurityDecisionCode.LEASE_NOT_ACTIVE,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                lease=replace(make_valid_snapshot().lease, state=LeaseState.EXPIRED),
            ),
            high_water(),
            SecurityDecisionCode.LEASE_EXPIRED,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                lease=replace(make_valid_snapshot().lease, state=LeaseState.REVOKED),
            ),
            high_water(),
            SecurityDecisionCode.LEASE_REVOKED,
        ),
        (
            make_valid_snapshot,
            high_water(expected_fencing_token=FencingToken(8)),
            SecurityDecisionCode.FENCING_MISMATCH,
        ),
        (
            make_valid_snapshot,
            high_water(minimum_fencing_token=FencingToken(8)),
            SecurityDecisionCode.FENCING_MISMATCH,
        ),
        (
            lambda: replace(make_valid_snapshot(), active_locks=(make_lock("lock-1"),)),
            high_water(),
            SecurityDecisionCode.LOCK_ACTIVE,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                active_locks=(make_lock("lock-1"), make_lock("lock-2")),
            ),
            high_water(),
            SecurityDecisionCode.MULTIPLE_LOCKS_ACTIVE,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                clock=replace(
                    make_valid_snapshot().clock,
                    confidence=ClockConfidence.UNTRUSTED,
                ),
            ),
            high_water(),
            SecurityDecisionCode.CLOCK_UNTRUSTED,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                recovery=RecoveryEvidence(
                    RecoveryActivity.RECOVERY_ACTIVE,
                    RecoveryId("recovery-1"),
                    verified_envelope(),
                ),
            ),
            high_water(),
            SecurityDecisionCode.RECOVERY_ACTIVE,
        ),
        (
            lambda: replace(
                make_valid_snapshot(),
                recovery=RecoveryEvidence(
                    RecoveryActivity.BACKFILL_ACTIVE,
                    RecoveryId("recovery-1"),
                    verified_envelope(),
                ),
            ),
            high_water(),
            SecurityDecisionCode.RECOVERY_ACTIVE,
        ),
        (
            make_valid_snapshot,
            high_water(minimum_revocation_generation=4),
            SecurityDecisionCode.EVIDENCE_CONFLICT,
        ),
    ),
)
def test_decision_matrix_blocks_each_security_gate(snapshot_factory, marks, expected):
    decision = evaluate(snapshot_factory(), marks=marks)
    assert decision.code is expected
    assert decision.all_security_gates_passed is False


def test_authentication_failed_state_is_blocked():
    snapshot = make_valid_snapshot()
    changed = replace(
        snapshot,
        authentication=replace(snapshot.authentication, state=AuthenticationState.REJECTED),
    )
    assert evaluate(changed).code is SecurityDecisionCode.AUTHENTICATION_INVALID


def test_conflicting_component_identity_has_deterministic_priority():
    snapshot = make_valid_snapshot()
    conflict = replace(
        snapshot,
        heartbeat=replace(snapshot.heartbeat, source_id=SourceId("source-conflict")),
    )
    assert evaluate(conflict).code is SecurityDecisionCode.EVIDENCE_CONFLICT


def test_primary_reason_and_secondary_order_are_deterministic():
    snapshot = make_valid_snapshot()
    broken = replace(
        snapshot,
        generation=1,
        clock=replace(snapshot.clock, confidence=ClockConfidence.UNTRUSTED),
        active_locks=(make_lock("lock-1"),),
    )
    first = evaluate(broken)
    second = evaluate(broken)
    assert first == second
    assert first.code is SecurityDecisionCode.CONTEXT_GENERATION_ROLLBACK
    assert first.secondary_codes == (
        SecurityDecisionCode.CLOCK_UNTRUSTED,
        SecurityDecisionCode.LOCK_ACTIVE,
    )


def test_explicit_monotonic_wall_clock_skew_is_blocked():
    decision = evaluate_security_context(
        make_valid_snapshot(),
        context_failure=None,
        evaluated_at_utc=NOW,
        monotonic_observation_ns=MONOTONIC_NOW_NS + 1_000_000_000,
        freshness_policy=freshness(),
        high_water_marks=high_water(),
    )
    assert decision.code is SecurityDecisionCode.CLOCK_UNTRUSTED


@pytest.mark.parametrize(
    "failure",
    (
        SecurityDecisionCode.CONTEXT_MISSING,
        SecurityDecisionCode.CONTEXT_VERSION_UNSUPPORTED,
        SecurityDecisionCode.CONTEXT_INCOMPLETE,
        SecurityDecisionCode.PROVIDER_FAILURE,
    ),
)
def test_acquisition_failures_are_fail_closed(failure):
    decision = evaluate(snapshot=None, context_failure=failure)
    assert decision.code is failure
    assert decision.context_verified is False
    assert decision.all_security_gates_passed is False
