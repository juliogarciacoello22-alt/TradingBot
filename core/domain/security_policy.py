"""Pure shadow policy for externally supplied security-context evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from core.domain.common import normalize_utc
from core.domain.errors import InvariantViolationError
from core.domain.identifiers import BootId, FencingToken, SourceId
from core.domain.security import AuthenticationState, LeaseState
from core.domain.security_context import (
    SECURITY_CONTEXT_SCHEMA_VERSION,
    ClockConfidence,
    EvidenceVerificationState,
    RecoveryActivity,
    SecurityContextSnapshot,
    VerificationEnvelope,
)


SECURITY_POLICY_VERSION = "1.0"


class SecurityDecisionCode(str, Enum):
    CONTEXT_MISSING = "SECURITY.CONTEXT_MISSING"
    CONTEXT_INCOMPLETE = "SECURITY.CONTEXT_INCOMPLETE"
    CONTEXT_UNVERIFIED = "SECURITY.CONTEXT_UNVERIFIED"
    CONTEXT_VERSION_UNSUPPORTED = "SECURITY.CONTEXT_VERSION_UNSUPPORTED"
    CONTEXT_GENERATION_ROLLBACK = "SECURITY.CONTEXT_GENERATION_ROLLBACK"
    CLOCK_UNTRUSTED = "SECURITY.CLOCK_UNTRUSTED"
    SOURCE_UNAUTHORIZED = "SECURITY.SOURCE_UNAUTHORIZED"
    BOOT_MISMATCH = "SECURITY.BOOT_MISMATCH"
    AUTHORITY_MISSING = "SECURITY.AUTHORITY_MISSING"
    AUTHORITY_UNVERIFIED = "SECURITY.AUTHORITY_UNVERIFIED"
    AUTHORITY_EXPIRED = "SECURITY.AUTHORITY_EXPIRED"
    AUTHENTICATION_INVALID = "SECURITY.AUTHENTICATION_INVALID"
    HEARTBEAT_MISSING = "SECURITY.HEARTBEAT_MISSING"
    HEARTBEAT_STALE = "SECURITY.HEARTBEAT_STALE"
    LEASE_MISSING = "SECURITY.LEASE_MISSING"
    LEASE_NOT_ACTIVE = "SECURITY.LEASE_NOT_ACTIVE"
    LEASE_EXPIRED = "SECURITY.LEASE_EXPIRED"
    LEASE_REVOKED = "SECURITY.LEASE_REVOKED"
    FENCING_MISMATCH = "SECURITY.FENCING_MISMATCH"
    LOCK_ACTIVE = "SECURITY.LOCK_ACTIVE"
    MULTIPLE_LOCKS_ACTIVE = "SECURITY.MULTIPLE_LOCKS_ACTIVE"
    EVIDENCE_CONFLICT = "SECURITY.EVIDENCE_CONFLICT"
    RECOVERY_ACTIVE = "SECURITY.RECOVERY_ACTIVE"
    PROVIDER_FAILURE = "SECURITY.PROVIDER_FAILURE"
    SHADOW_PASS = "SECURITY.SHADOW_PASS"


class SecuritySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SecurityDisposition(str, Enum):
    BLOCKED = "BLOCKED"
    SHADOW_SECURITY_PASS = "SHADOW_SECURITY_PASS"


class SecurityGateName(str, Enum):
    CONTEXT_AVAILABILITY = "CONTEXT_AVAILABILITY"
    SCHEMA_VERSION = "SCHEMA_VERSION"
    CONTEXT_INTEGRITY = "CONTEXT_INTEGRITY"
    CONTEXT_VERIFICATION = "CONTEXT_VERIFICATION"
    CONTEXT_GENERATION = "CONTEXT_GENERATION"
    EVIDENCE_CONSISTENCY = "EVIDENCE_CONSISTENCY"
    CLOCK = "CLOCK"
    SOURCE = "SOURCE"
    BOOT = "BOOT"
    AUTHORITY = "AUTHORITY"
    AUTHENTICATION = "AUTHENTICATION"
    REVOCATION = "REVOCATION"
    LEASE = "LEASE"
    FENCING = "FENCING"
    HEARTBEAT = "HEARTBEAT"
    LOCKS = "LOCKS"
    RECOVERY = "RECOVERY"
    SHADOW_RESULT = "SHADOW_RESULT"


_CODE_SEVERITY = {
    SecurityDecisionCode.SHADOW_PASS: SecuritySeverity.INFO,
    SecurityDecisionCode.CONTEXT_MISSING: SecuritySeverity.HIGH,
    SecurityDecisionCode.CONTEXT_INCOMPLETE: SecuritySeverity.HIGH,
    SecurityDecisionCode.CONTEXT_UNVERIFIED: SecuritySeverity.HIGH,
    SecurityDecisionCode.CONTEXT_VERSION_UNSUPPORTED: SecuritySeverity.HIGH,
    SecurityDecisionCode.CONTEXT_GENERATION_ROLLBACK: SecuritySeverity.CRITICAL,
    SecurityDecisionCode.CLOCK_UNTRUSTED: SecuritySeverity.HIGH,
    SecurityDecisionCode.SOURCE_UNAUTHORIZED: SecuritySeverity.CRITICAL,
    SecurityDecisionCode.BOOT_MISMATCH: SecuritySeverity.CRITICAL,
    SecurityDecisionCode.AUTHORITY_MISSING: SecuritySeverity.HIGH,
    SecurityDecisionCode.AUTHORITY_UNVERIFIED: SecuritySeverity.HIGH,
    SecurityDecisionCode.AUTHORITY_EXPIRED: SecuritySeverity.HIGH,
    SecurityDecisionCode.AUTHENTICATION_INVALID: SecuritySeverity.HIGH,
    SecurityDecisionCode.HEARTBEAT_MISSING: SecuritySeverity.HIGH,
    SecurityDecisionCode.HEARTBEAT_STALE: SecuritySeverity.HIGH,
    SecurityDecisionCode.LEASE_MISSING: SecuritySeverity.HIGH,
    SecurityDecisionCode.LEASE_NOT_ACTIVE: SecuritySeverity.HIGH,
    SecurityDecisionCode.LEASE_EXPIRED: SecuritySeverity.HIGH,
    SecurityDecisionCode.LEASE_REVOKED: SecuritySeverity.CRITICAL,
    SecurityDecisionCode.FENCING_MISMATCH: SecuritySeverity.CRITICAL,
    SecurityDecisionCode.LOCK_ACTIVE: SecuritySeverity.CRITICAL,
    SecurityDecisionCode.MULTIPLE_LOCKS_ACTIVE: SecuritySeverity.CRITICAL,
    SecurityDecisionCode.EVIDENCE_CONFLICT: SecuritySeverity.CRITICAL,
    SecurityDecisionCode.RECOVERY_ACTIVE: SecuritySeverity.HIGH,
    SecurityDecisionCode.PROVIDER_FAILURE: SecuritySeverity.HIGH,
}

_SEVERITY_RANK = {
    SecuritySeverity.INFO: 0,
    SecuritySeverity.WARNING: 1,
    SecuritySeverity.HIGH: 2,
    SecuritySeverity.CRITICAL: 3,
}

_CONTEXT_FAILURE_CODES = frozenset(
    {
        SecurityDecisionCode.CONTEXT_MISSING,
        SecurityDecisionCode.CONTEXT_INCOMPLETE,
        SecurityDecisionCode.CONTEXT_UNVERIFIED,
        SecurityDecisionCode.CONTEXT_VERSION_UNSUPPORTED,
        SecurityDecisionCode.EVIDENCE_CONFLICT,
        SecurityDecisionCode.PROVIDER_FAILURE,
    }
)


@dataclass(frozen=True)
class SecurityFreshnessPolicy:
    heartbeat_max_age: timedelta
    authority_max_age: timedelta
    authentication_max_age: timedelta
    revocation_max_age: timedelta
    allowed_clock_skew: timedelta
    lease_expiry_margin: timedelta

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not isinstance(value, timedelta) or value < timedelta(0):
                raise InvariantViolationError(f"{name} must be a non-negative timedelta")


@dataclass(frozen=True)
class SecurityHighWaterMarks:
    expected_source_id: SourceId | None
    authorized_source_ids: tuple[SourceId, ...]
    expected_boot_id: BootId | None
    minimum_context_generation: int
    minimum_heartbeat_sequence: int | None
    expected_fencing_token: FencingToken | None
    minimum_fencing_token: FencingToken | None
    minimum_revocation_generation: int | None

    def __post_init__(self) -> None:
        if self.expected_source_id is not None and not isinstance(
            self.expected_source_id, SourceId
        ):
            raise InvariantViolationError("expected_source_id is invalid")
        if self.expected_boot_id is not None and not isinstance(
            self.expected_boot_id, BootId
        ):
            raise InvariantViolationError("expected_boot_id is invalid")
        for name in ("expected_fencing_token", "minimum_fencing_token"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, FencingToken):
                raise InvariantViolationError(f"{name} is invalid")
        if not isinstance(self.authorized_source_ids, tuple) or not all(
            isinstance(item, SourceId) for item in self.authorized_source_ids
        ):
            raise InvariantViolationError("authorized_source_ids contains an invalid value")
        sources = tuple(sorted(set(self.authorized_source_ids)))
        object.__setattr__(self, "authorized_source_ids", sources)
        if (
            isinstance(self.minimum_context_generation, bool)
            or not isinstance(self.minimum_context_generation, int)
            or self.minimum_context_generation < 0
        ):
            raise InvariantViolationError("minimum_context_generation must be non-negative")
        for name in ("minimum_heartbeat_sequence", "minimum_revocation_generation"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise InvariantViolationError(f"{name} must be non-negative")


@dataclass(frozen=True)
class SecurityGateResult:
    gate: SecurityGateName
    passed: bool | None
    code: SecurityDecisionCode | None
    severity: SecuritySeverity
    evidence_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.passed is True and self.code is not None:
            raise InvariantViolationError("a passed gate cannot have a failure code")
        if self.passed is None and self.code is not None:
            raise InvariantViolationError("an unevaluated gate cannot have a failure code")
        if self.passed is False and self.code is None and self.gate is not SecurityGateName.SHADOW_RESULT:
            raise InvariantViolationError("a failed gate requires a failure code")


@dataclass(frozen=True)
class SecurityPolicyAuditData:
    policy_version: str
    context_id: str | None
    context_hash: str | None
    context_generation: int | None
    security_code: SecurityDecisionCode
    secondary_security_codes: tuple[SecurityDecisionCode, ...]
    evidence_hashes: tuple[str, ...]
    source_id: str | None
    boot_id: str | None
    evaluated_at_utc: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "context_id": self.context_id,
            "context_hash": self.context_hash,
            "context_generation": self.context_generation,
            "security_code": self.security_code.value,
            "secondary_security_codes": tuple(
                item.value for item in self.secondary_security_codes
            ),
            "evidence_hashes": self.evidence_hashes,
            "source_id": self.source_id,
            "boot_id": self.boot_id,
            "evaluated_at_utc": self.evaluated_at_utc,
        }


@dataclass(frozen=True)
class SecurityPolicyDecision:
    context_verified: bool
    all_security_gates_passed: bool
    disposition: SecurityDisposition
    code: SecurityDecisionCode
    secondary_codes: tuple[SecurityDecisionCode, ...]
    severity: SecuritySeverity
    gate_results: tuple[SecurityGateResult, ...]
    evidence_hashes: tuple[str, ...]
    audit_data: SecurityPolicyAuditData

    def __post_init__(self) -> None:
        if self.all_security_gates_passed != (
            self.disposition is SecurityDisposition.SHADOW_SECURITY_PASS
        ):
            raise InvariantViolationError("security disposition contradicts gate result")
        if self.all_security_gates_passed != (self.code is SecurityDecisionCode.SHADOW_PASS):
            raise InvariantViolationError("shadow pass code contradicts gate result")


def evaluate_security_context(
    snapshot: SecurityContextSnapshot | None,
    *,
    context_failure: SecurityDecisionCode | None,
    evaluated_at_utc: datetime,
    monotonic_observation_ns: int | None,
    freshness_policy: SecurityFreshnessPolicy,
    high_water_marks: SecurityHighWaterMarks,
) -> SecurityPolicyDecision:
    """Evaluate supplied evidence without granting operational permission."""

    evaluated_at = normalize_utc(evaluated_at_utc, field_name="evaluated_at_utc")
    if monotonic_observation_ns is not None and (
        isinstance(monotonic_observation_ns, bool)
        or not isinstance(monotonic_observation_ns, int)
        or monotonic_observation_ns < 0
    ):
        raise InvariantViolationError("monotonic_observation_ns must be non-negative")
    if (snapshot is None) == (context_failure is None):
        raise InvariantViolationError(
            "exactly one of snapshot or context_failure must be supplied"
        )
    if context_failure is not None and context_failure not in _CONTEXT_FAILURE_CODES:
        raise InvariantViolationError("context_failure is not an acquisition failure code")

    outcomes: dict[SecurityGateName, SecurityDecisionCode | bool | None] = {
        gate: None for gate in SecurityGateName
    }
    if snapshot is None:
        outcomes[SecurityGateName.CONTEXT_AVAILABILITY] = context_failure
        outcomes[SecurityGateName.SHADOW_RESULT] = False
        return _build_decision(outcomes, None, evaluated_at, context_verified=False)

    outcomes[SecurityGateName.CONTEXT_AVAILABILITY] = True
    outcomes[SecurityGateName.SCHEMA_VERSION] = (
        True
        if snapshot.schema_version == SECURITY_CONTEXT_SCHEMA_VERSION
        else SecurityDecisionCode.CONTEXT_VERSION_UNSUPPORTED
    )
    outcomes[SecurityGateName.CONTEXT_INTEGRITY] = True

    envelopes = _required_verification_envelopes(snapshot)
    all_components_verified = all(
        item.state is EvidenceVerificationState.VERIFIED for item in envelopes
    )
    if snapshot.overall_verification is EvidenceVerificationState.REJECTED:
        verification_code = SecurityDecisionCode.EVIDENCE_CONFLICT
    elif (
        snapshot.overall_verification is not EvidenceVerificationState.VERIFIED
        or not all_components_verified
    ):
        verification_code = SecurityDecisionCode.CONTEXT_UNVERIFIED
    else:
        verification_code = None
    context_verified = verification_code is None
    outcomes[SecurityGateName.CONTEXT_VERIFICATION] = verification_code or True

    outcomes[SecurityGateName.CONTEXT_GENERATION] = (
        SecurityDecisionCode.CONTEXT_GENERATION_ROLLBACK
        if snapshot.generation < high_water_marks.minimum_context_generation
        else True
    )
    outcomes[SecurityGateName.EVIDENCE_CONSISTENCY] = (
        SecurityDecisionCode.EVIDENCE_CONFLICT
        if _has_evidence_conflict(snapshot)
        else True
    )
    outcomes[SecurityGateName.CLOCK] = (
        True
        if _clock_is_trusted(
            snapshot,
            evaluated_at,
            monotonic_observation_ns,
            freshness_policy.allowed_clock_skew,
        )
        else SecurityDecisionCode.CLOCK_UNTRUSTED
    )
    outcomes[SecurityGateName.SOURCE] = (
        True
        if _source_is_authorized(snapshot, high_water_marks)
        else SecurityDecisionCode.SOURCE_UNAUTHORIZED
    )
    outcomes[SecurityGateName.BOOT] = (
        True
        if _boot_matches(snapshot, high_water_marks)
        else SecurityDecisionCode.BOOT_MISMATCH
    )
    outcomes[SecurityGateName.AUTHORITY] = _authority_outcome(
        snapshot, evaluated_at, freshness_policy
    )
    outcomes[SecurityGateName.AUTHENTICATION] = _authentication_outcome(
        snapshot, evaluated_at, freshness_policy
    )
    outcomes[SecurityGateName.REVOCATION] = _revocation_outcome(
        snapshot, evaluated_at, freshness_policy, high_water_marks
    )
    outcomes[SecurityGateName.LEASE] = _lease_outcome(
        snapshot, evaluated_at, freshness_policy
    )
    outcomes[SecurityGateName.FENCING] = (
        True
        if _fencing_matches(snapshot, high_water_marks)
        else SecurityDecisionCode.FENCING_MISMATCH
    )
    outcomes[SecurityGateName.HEARTBEAT] = _heartbeat_outcome(
        snapshot, evaluated_at, freshness_policy, high_water_marks
    )
    if len(snapshot.active_locks) > 1:
        outcomes[SecurityGateName.LOCKS] = SecurityDecisionCode.MULTIPLE_LOCKS_ACTIVE
    elif snapshot.active_locks:
        outcomes[SecurityGateName.LOCKS] = SecurityDecisionCode.LOCK_ACTIVE
    else:
        outcomes[SecurityGateName.LOCKS] = True
    outcomes[SecurityGateName.RECOVERY] = (
        True
        if snapshot.recovery.activity is RecoveryActivity.CLEAR
        else SecurityDecisionCode.RECOVERY_ACTIVE
    )

    failures = [
        value
        for gate, value in outcomes.items()
        if gate is not SecurityGateName.SHADOW_RESULT
        and isinstance(value, SecurityDecisionCode)
    ]
    outcomes[SecurityGateName.SHADOW_RESULT] = not failures
    return _build_decision(outcomes, snapshot, evaluated_at, context_verified=context_verified)


def _required_verification_envelopes(
    snapshot: SecurityContextSnapshot,
) -> tuple[VerificationEnvelope, ...]:
    return (
        snapshot.source_verification,
        snapshot.boot_verification,
        snapshot.authority_verification,
        snapshot.authentication_verification,
        snapshot.heartbeat_verification,
        snapshot.lease_verification,
        snapshot.fencing_verification,
        snapshot.clock.verification,
        snapshot.revocation_verification,
        snapshot.recovery.verification,
        *(item.verification for item in snapshot.active_locks),
    )


def _has_evidence_conflict(snapshot: SecurityContextSnapshot) -> bool:
    source_ids = []
    boot_ids = []
    fencing_tokens = []
    if snapshot.source_identity is not None:
        source_ids.append(snapshot.source_identity.source_id)
    if snapshot.boot_identity is not None:
        source_ids.append(snapshot.boot_identity.source_id)
        boot_ids.append(snapshot.boot_identity.boot_id)
    if snapshot.authentication is not None:
        source_ids.append(snapshot.authentication.source_id)
        boot_ids.append(snapshot.authentication.boot_id)
    if snapshot.heartbeat is not None:
        source_ids.append(snapshot.heartbeat.source_id)
        boot_ids.append(snapshot.heartbeat.boot_id)
        fencing_tokens.append(snapshot.heartbeat.fencing_token)
    if snapshot.lease is not None:
        source_ids.append(snapshot.lease.source_id)
        boot_ids.append(snapshot.lease.boot_id)
        fencing_tokens.append(snapshot.lease.fencing_token)
    if snapshot.fencing_token is not None:
        fencing_tokens.append(snapshot.fencing_token)
    return any(
        len(set(values)) > 1 for values in (source_ids, boot_ids, fencing_tokens)
    )


def _clock_is_trusted(
    snapshot: SecurityContextSnapshot,
    evaluated_at: datetime,
    monotonic_observation_ns: int | None,
    allowed_skew: timedelta,
) -> bool:
    clock = snapshot.clock
    if (
        clock.confidence is not ClockConfidence.TRUSTED
        or clock.verification.state is not EvidenceVerificationState.VERIFIED
        or clock.observed_at_utc is None
        or clock.monotonic_ns is None
        or monotonic_observation_ns is None
        or monotonic_observation_ns < clock.monotonic_ns
    ):
        return False
    wall_elapsed = (evaluated_at - clock.observed_at_utc).total_seconds()
    monotonic_elapsed = (monotonic_observation_ns - clock.monotonic_ns) / 1_000_000_000
    return abs(wall_elapsed - monotonic_elapsed) <= allowed_skew.total_seconds()


def _source_is_authorized(
    snapshot: SecurityContextSnapshot,
    high_water_marks: SecurityHighWaterMarks,
) -> bool:
    if snapshot.source_identity is None:
        return False
    source_id = snapshot.source_identity.source_id
    if high_water_marks.expected_source_id is not None and source_id != high_water_marks.expected_source_id:
        return False
    return not high_water_marks.authorized_source_ids or source_id in high_water_marks.authorized_source_ids


def _boot_matches(
    snapshot: SecurityContextSnapshot,
    high_water_marks: SecurityHighWaterMarks,
) -> bool:
    if snapshot.boot_identity is None:
        return False
    return high_water_marks.expected_boot_id is None or (
        snapshot.boot_identity.boot_id == high_water_marks.expected_boot_id
    )


def _authority_outcome(
    snapshot: SecurityContextSnapshot,
    evaluated_at: datetime,
    freshness_policy: SecurityFreshnessPolicy,
) -> bool | SecurityDecisionCode:
    authority = snapshot.authority_assertion
    if authority is None:
        return SecurityDecisionCode.AUTHORITY_MISSING
    envelope = snapshot.authority_verification
    if not authority.verified or envelope.state is not EvidenceVerificationState.VERIFIED:
        return SecurityDecisionCode.AUTHORITY_UNVERIFIED
    if (
        evaluated_at - authority.asserted_at > freshness_policy.authority_max_age
        or (envelope.valid_until_utc is not None and evaluated_at >= envelope.valid_until_utc)
    ):
        return SecurityDecisionCode.AUTHORITY_EXPIRED
    return True


def _authentication_outcome(
    snapshot: SecurityContextSnapshot,
    evaluated_at: datetime,
    freshness_policy: SecurityFreshnessPolicy,
) -> bool | SecurityDecisionCode:
    authentication = snapshot.authentication
    envelope = snapshot.authentication_verification
    if (
        authentication is None
        or authentication.state is not AuthenticationState.VERIFIED
        or envelope.state is not EvidenceVerificationState.VERIFIED
        or evaluated_at - authentication.assessed_at > freshness_policy.authentication_max_age
        or (envelope.valid_until_utc is not None and evaluated_at >= envelope.valid_until_utc)
    ):
        return SecurityDecisionCode.AUTHENTICATION_INVALID
    return True


def _revocation_outcome(
    snapshot: SecurityContextSnapshot,
    evaluated_at: datetime,
    freshness_policy: SecurityFreshnessPolicy,
    high_water_marks: SecurityHighWaterMarks,
) -> bool | SecurityDecisionCode:
    envelope = snapshot.revocation_verification
    if snapshot.revocation_generation is None:
        return SecurityDecisionCode.CONTEXT_INCOMPLETE
    if envelope.state is not EvidenceVerificationState.VERIFIED or envelope.verified_at_utc is None:
        return SecurityDecisionCode.CONTEXT_UNVERIFIED
    if evaluated_at - envelope.verified_at_utc > freshness_policy.revocation_max_age:
        return SecurityDecisionCode.CONTEXT_UNVERIFIED
    minimum = high_water_marks.minimum_revocation_generation
    if minimum is not None and snapshot.revocation_generation < minimum:
        return SecurityDecisionCode.EVIDENCE_CONFLICT
    return True


def _lease_outcome(
    snapshot: SecurityContextSnapshot,
    evaluated_at: datetime,
    freshness_policy: SecurityFreshnessPolicy,
) -> bool | SecurityDecisionCode:
    lease = snapshot.lease
    if lease is None:
        return SecurityDecisionCode.LEASE_MISSING
    if lease.state is LeaseState.REVOKED:
        return SecurityDecisionCode.LEASE_REVOKED
    if lease.state is LeaseState.EXPIRED or evaluated_at + freshness_policy.lease_expiry_margin >= lease.expires_at:
        return SecurityDecisionCode.LEASE_EXPIRED
    if lease.state is not LeaseState.ACTIVE:
        return SecurityDecisionCode.LEASE_NOT_ACTIVE
    return True


def _fencing_matches(
    snapshot: SecurityContextSnapshot,
    high_water_marks: SecurityHighWaterMarks,
) -> bool:
    token = snapshot.fencing_token
    if token is None:
        return False
    if high_water_marks.expected_fencing_token is not None and token != high_water_marks.expected_fencing_token:
        return False
    if high_water_marks.minimum_fencing_token is not None and token.value < high_water_marks.minimum_fencing_token.value:
        return False
    return True


def _heartbeat_outcome(
    snapshot: SecurityContextSnapshot,
    evaluated_at: datetime,
    freshness_policy: SecurityFreshnessPolicy,
    high_water_marks: SecurityHighWaterMarks,
) -> bool | SecurityDecisionCode:
    heartbeat = snapshot.heartbeat
    if heartbeat is None:
        return SecurityDecisionCode.HEARTBEAT_MISSING
    if evaluated_at - heartbeat.observed_at > freshness_policy.heartbeat_max_age:
        return SecurityDecisionCode.HEARTBEAT_STALE
    minimum = high_water_marks.minimum_heartbeat_sequence
    if minimum is not None and heartbeat.sequence < minimum:
        return SecurityDecisionCode.HEARTBEAT_STALE
    return True


def _collect_evidence_hashes(snapshot: SecurityContextSnapshot | None) -> tuple[str, ...]:
    if snapshot is None:
        return ()
    hashes = {item.sha256 for item in snapshot.evidence_references}
    for envelope in _required_verification_envelopes(snapshot):
        hashes.update(envelope.evidence_hashes)
    return tuple(sorted(hashes))


def _build_decision(
    outcomes: dict[SecurityGateName, SecurityDecisionCode | bool | None],
    snapshot: SecurityContextSnapshot | None,
    evaluated_at: datetime,
    *,
    context_verified: bool,
) -> SecurityPolicyDecision:
    failures = [
        value
        for gate, value in outcomes.items()
        if gate is not SecurityGateName.SHADOW_RESULT
        and isinstance(value, SecurityDecisionCode)
    ]
    unique_failures = tuple(dict.fromkeys(failures))
    passed = not unique_failures
    code = SecurityDecisionCode.SHADOW_PASS if passed else unique_failures[0]
    secondary = () if passed else unique_failures[1:]
    severity = max(
        (_CODE_SEVERITY[item] for item in unique_failures),
        key=lambda item: _SEVERITY_RANK[item],
        default=SecuritySeverity.INFO,
    )
    evidence_hashes = _collect_evidence_hashes(snapshot)
    results = []
    for gate in SecurityGateName:
        value = outcomes[gate]
        if isinstance(value, SecurityDecisionCode):
            results.append(
                SecurityGateResult(
                    gate=gate,
                    passed=False,
                    code=value,
                    severity=_CODE_SEVERITY[value],
                    evidence_hashes=evidence_hashes,
                )
            )
        elif value is True:
            results.append(
                SecurityGateResult(gate, True, None, SecuritySeverity.INFO, ())
            )
        elif value is False:
            results.append(
                SecurityGateResult(gate, False, None, severity, evidence_hashes)
            )
        else:
            results.append(
                SecurityGateResult(gate, None, None, SecuritySeverity.INFO, ())
            )

    source_id = (
        snapshot.source_identity.source_id.value
        if snapshot is not None and snapshot.source_identity is not None
        else None
    )
    boot_id = (
        snapshot.boot_identity.boot_id.value
        if snapshot is not None and snapshot.boot_identity is not None
        else None
    )
    audit_data = SecurityPolicyAuditData(
        policy_version=SECURITY_POLICY_VERSION,
        context_id=None if snapshot is None else snapshot.context_id.value,
        context_hash=None if snapshot is None else snapshot.context_hash,
        context_generation=None if snapshot is None else snapshot.generation,
        security_code=code,
        secondary_security_codes=secondary,
        evidence_hashes=evidence_hashes,
        source_id=source_id,
        boot_id=boot_id,
        evaluated_at_utc=evaluated_at,
    )
    return SecurityPolicyDecision(
        context_verified=context_verified,
        all_security_gates_passed=passed,
        disposition=(
            SecurityDisposition.SHADOW_SECURITY_PASS
            if passed
            else SecurityDisposition.BLOCKED
        ),
        code=code,
        secondary_codes=secondary,
        severity=severity,
        gate_results=tuple(results),
        evidence_hashes=evidence_hashes,
        audit_data=audit_data,
    )
