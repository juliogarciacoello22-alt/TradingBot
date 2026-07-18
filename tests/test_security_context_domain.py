from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone

import pytest

from core.domain.identifiers import (
    BootId,
    EventId,
    FencingToken,
    LeaseId,
    RecoveryId,
    SourceId,
)
from core.domain.security import (
    AuthenticationRecord,
    AuthenticationState,
    AuthorityAssertion,
    AuthorityRole,
    BootIdentity,
    Heartbeat,
    Lease,
    LeaseState,
    LockState,
    SecurityLock,
    SourceIdentity,
)
from core.domain.security_context import (
    SECURITY_CONTEXT_SCHEMA_VERSION,
    ClockConfidence,
    ClockEvidence,
    ContextId,
    EvidenceReference,
    EvidenceVerificationState,
    RecoveryActivity,
    RecoveryEvidence,
    SecurityContextSnapshot,
    SecurityContextValidationError,
    SecurityEvidenceKind,
    UnsupportedSecurityContextVersionError,
    VerificationEnvelope,
    VerifiedSecurityLock,
)


NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
MONOTONIC_NOW_NS = 10_000_000_000
HASH_A = "a" * 64
HASH_B = "b" * 64


def verified_envelope(
    evidence_hash: str = HASH_A,
    *,
    verified_at: datetime = NOW - timedelta(seconds=10),
    valid_until: datetime | None = NOW + timedelta(minutes=5),
) -> VerificationEnvelope:
    return VerificationEnvelope(
        state=EvidenceVerificationState.VERIFIED,
        evidence_hashes=(evidence_hash,),
        verified_at_utc=verified_at,
        valid_until_utc=valid_until,
        verifier_id="security-controller-1",
    )


def make_valid_snapshot(**overrides) -> SecurityContextSnapshot:
    source_id = SourceId("source-1")
    boot_id = BootId("boot-1")
    fencing = FencingToken(7)
    values = {
        "schema_version": SECURITY_CONTEXT_SCHEMA_VERSION,
        "context_id": ContextId("context-1"),
        "generation": 4,
        "overall_verification": EvidenceVerificationState.VERIFIED,
        "source_identity": SourceIdentity(source_id, "principal-1"),
        "source_verification": verified_envelope(),
        "boot_identity": BootIdentity(boot_id, source_id, NOW - timedelta(minutes=2)),
        "boot_verification": verified_envelope(),
        "authority_assertion": AuthorityAssertion(
            actor="controller-1",
            role=AuthorityRole.SECURITY_CONTROLLER,
            asserted_at=NOW - timedelta(seconds=10),
            evidence_hashes=(HASH_A,),
            verified=True,
        ),
        "authority_verification": verified_envelope(),
        "authentication": AuthenticationRecord(
            source_id=source_id,
            boot_id=boot_id,
            state=AuthenticationState.VERIFIED,
            assessed_at=NOW - timedelta(seconds=10),
            mechanism="signed-challenge",
            evidence_hashes=(HASH_A,),
        ),
        "authentication_verification": verified_envelope(),
        "heartbeat": Heartbeat(
            event_id=EventId("heartbeat-1"),
            source_id=source_id,
            boot_id=boot_id,
            fencing_token=fencing,
            sequence=12,
            observed_at=NOW - timedelta(seconds=5),
        ),
        "heartbeat_verification": verified_envelope(),
        "lease": Lease(
            lease_id=LeaseId("lease-1"),
            source_id=source_id,
            boot_id=boot_id,
            fencing_token=fencing,
            issued_at=NOW - timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=1),
            state=LeaseState.ACTIVE,
        ),
        "lease_verification": verified_envelope(),
        "fencing_token": fencing,
        "fencing_verification": verified_envelope(),
        "active_locks": (),
        "clock": ClockEvidence(
            confidence=ClockConfidence.TRUSTED,
            observed_at_utc=NOW - timedelta(seconds=5),
            monotonic_ns=5_000_000_000,
            verification=verified_envelope(),
        ),
        "revocation_generation": 3,
        "revocation_verification": verified_envelope(
            verified_at=NOW - timedelta(seconds=5)
        ),
        "recovery": RecoveryEvidence(
            activity=RecoveryActivity.CLEAR,
            recovery_id=None,
            verification=verified_envelope(),
        ),
        "evidence_references": (
            EvidenceReference(SecurityEvidenceKind.AUTHORITY, HASH_A),
            EvidenceReference(SecurityEvidenceKind.AUTHENTICATION, HASH_B),
        ),
    }
    values.update(overrides)
    return SecurityContextSnapshot(**values)


def make_lock(event_id: str) -> VerifiedSecurityLock:
    return VerifiedSecurityLock(
        SecurityLock(EventId(event_id), LockState.LOCKED, NOW, "incident-lock"),
        verified_envelope(),
    )


def test_snapshot_has_frozen_field_order_of_twenty_five_fields():
    assert tuple(item.name for item in fields(SecurityContextSnapshot)) == (
        "schema_version",
        "context_id",
        "generation",
        "overall_verification",
        "source_identity",
        "source_verification",
        "boot_identity",
        "boot_verification",
        "authority_assertion",
        "authority_verification",
        "authentication",
        "authentication_verification",
        "heartbeat",
        "heartbeat_verification",
        "lease",
        "lease_verification",
        "fencing_token",
        "fencing_verification",
        "active_locks",
        "clock",
        "revocation_generation",
        "revocation_verification",
        "recovery",
        "evidence_references",
        "context_hash",
    )
    snapshot = make_valid_snapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.generation = 5


def test_context_identity_and_generation_are_explicit_and_positive():
    with pytest.raises(SecurityContextValidationError):
        ContextId("bad context id")
    with pytest.raises(SecurityContextValidationError):
        make_valid_snapshot(generation=0)
    with pytest.raises(SecurityContextValidationError):
        make_valid_snapshot(source_identity="synthetic-source")
    assert make_valid_snapshot().context_id == ContextId("context-1")


def test_direct_construction_accepts_schema_version_one():
    assert make_valid_snapshot(schema_version=1).schema_version == 1


@pytest.mark.parametrize("value", (True, "1", 1.0, None))
def test_direct_construction_rejects_non_integer_schema_version_with_exact_error(value):
    with pytest.raises(SecurityContextValidationError) as error:
        make_valid_snapshot(schema_version=value)
    assert type(error.value) is SecurityContextValidationError


@pytest.mark.parametrize("value", (0, 2))
def test_direct_construction_rejects_unsupported_integer_schema_version_with_exact_error(value):
    with pytest.raises(UnsupportedSecurityContextVersionError) as error:
        make_valid_snapshot(schema_version=value)
    assert type(error.value) is UnsupportedSecurityContextVersionError


def test_verification_states_cannot_claim_synthetic_verification_metadata():
    with pytest.raises(SecurityContextValidationError):
        VerificationEnvelope(
            EvidenceVerificationState.UNKNOWN,
            verified_at_utc=NOW,
            verifier_id="local",
        )
    with pytest.raises(SecurityContextValidationError):
        VerificationEnvelope(EvidenceVerificationState.VERIFIED)
    assert VerificationEnvelope(EvidenceVerificationState.NOT_VERIFIED).evidence_hashes == ()


def test_trusted_clock_requires_explicit_verified_wall_and_monotonic_observations():
    with pytest.raises(SecurityContextValidationError):
        ClockEvidence(
            ClockConfidence.TRUSTED,
            observed_at_utc=None,
            monotonic_ns=None,
            verification=VerificationEnvelope(EvidenceVerificationState.UNKNOWN),
        )


def test_active_locks_are_sorted_and_duplicate_ids_are_rejected():
    second = make_lock("lock-2")
    first = make_lock("lock-1")
    snapshot = make_valid_snapshot(active_locks=(second, first))
    assert tuple(item.lock.event_id.value for item in snapshot.active_locks) == (
        "lock-1",
        "lock-2",
    )
    with pytest.raises(SecurityContextValidationError):
        make_valid_snapshot(active_locks=(first, replace(first)))


def test_active_recovery_requires_explicit_recovery_identity():
    with pytest.raises(SecurityContextValidationError):
        RecoveryEvidence(
            RecoveryActivity.RECOVERY_ACTIVE,
            None,
            verified_envelope(),
        )
    evidence = RecoveryEvidence(
        RecoveryActivity.BACKFILL_ACTIVE,
        RecoveryId("recovery-1"),
        verified_envelope(),
    )
    assert evidence.activity is RecoveryActivity.BACKFILL_ACTIVE
