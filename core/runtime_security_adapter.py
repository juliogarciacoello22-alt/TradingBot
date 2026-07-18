"""Pure, non-operational adapter combining legacy and shadow decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from core.domain.security_policy import (
    SECURITY_POLICY_VERSION,
    SecurityDecisionCode,
    SecurityFreshnessPolicy,
    SecurityHighWaterMarks,
    SecurityPolicyDecision,
    evaluate_security_context,
)
from core.runtime_guard import ExecutionAuthorization
from core.security_context_provider import (
    ProviderFailureCode,
    SecurityContextProviderResult,
)


@dataclass(frozen=True)
class ShadowAuditPayload:
    policy_version: str
    context_id: str | None
    context_hash: str | None
    context_generation: int | None
    legacy_allowed: bool
    legacy_reason: str
    shadow_would_allow: bool
    primary_security_code: SecurityDecisionCode
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
            "legacy_allowed": self.legacy_allowed,
            "legacy_reason": self.legacy_reason,
            "shadow_would_allow": self.shadow_would_allow,
            "primary_security_code": self.primary_security_code.value,
            "secondary_security_codes": tuple(
                item.value for item in self.secondary_security_codes
            ),
            "evidence_hashes": self.evidence_hashes,
            "source_id": self.source_id,
            "boot_id": self.boot_id,
            "evaluated_at_utc": self.evaluated_at_utc,
        }


@dataclass(frozen=True)
class ShadowSecurityEvaluation:
    legacy_decision: ExecutionAuthorization
    security_decision: SecurityPolicyDecision
    operational_allowed: bool
    shadow_would_allow: bool
    audit_payload: ShadowAuditPayload

    def __post_init__(self) -> None:
        if self.operational_allowed != self.legacy_decision.allowed:
            raise ValueError("operational_allowed must remain identical to legacy")
        expected_shadow = (
            self.legacy_decision.allowed
            and self.security_decision.context_verified
            and self.security_decision.all_security_gates_passed
        )
        if self.shadow_would_allow != expected_shadow:
            raise ValueError("shadow_would_allow contradicts the frozen formula")


def evaluate_shadow_security(
    legacy_decision: ExecutionAuthorization,
    provider_result: SecurityContextProviderResult,
    *,
    evaluated_at_utc: datetime,
    monotonic_observation_ns: int | None,
    freshness_policy: SecurityFreshnessPolicy,
    high_water_marks: SecurityHighWaterMarks,
) -> ShadowSecurityEvaluation:
    """Return immutable diagnostics while preserving legacy authorization."""

    snapshot = provider_result.snapshot
    context_failure = (
        None
        if provider_result.failure is None
        else _map_provider_failure(provider_result.failure.code)
    )
    security_decision = evaluate_security_context(
        snapshot,
        context_failure=context_failure,
        evaluated_at_utc=evaluated_at_utc,
        monotonic_observation_ns=monotonic_observation_ns,
        freshness_policy=freshness_policy,
        high_water_marks=high_water_marks,
    )
    operational_allowed = legacy_decision.allowed
    shadow_would_allow = (
        legacy_decision.allowed
        and security_decision.context_verified
        and security_decision.all_security_gates_passed
    )
    audit = security_decision.audit_data
    audit_payload = ShadowAuditPayload(
        policy_version=SECURITY_POLICY_VERSION,
        context_id=audit.context_id,
        context_hash=audit.context_hash,
        context_generation=audit.context_generation,
        legacy_allowed=legacy_decision.allowed,
        legacy_reason=legacy_decision.reason,
        shadow_would_allow=shadow_would_allow,
        primary_security_code=security_decision.code,
        secondary_security_codes=security_decision.secondary_codes,
        evidence_hashes=security_decision.evidence_hashes,
        source_id=audit.source_id,
        boot_id=audit.boot_id,
        evaluated_at_utc=audit.evaluated_at_utc,
    )
    return ShadowSecurityEvaluation(
        legacy_decision=legacy_decision,
        security_decision=security_decision,
        operational_allowed=operational_allowed,
        shadow_would_allow=shadow_would_allow,
        audit_payload=audit_payload,
    )


def _map_provider_failure(code: ProviderFailureCode) -> SecurityDecisionCode:
    if code is ProviderFailureCode.UNSUPPORTED_VERSION:
        return SecurityDecisionCode.CONTEXT_VERSION_UNSUPPORTED
    if code is ProviderFailureCode.HASH_MISMATCH:
        return SecurityDecisionCode.EVIDENCE_CONFLICT
    if code in {ProviderFailureCode.PARTIAL_SNAPSHOT, ProviderFailureCode.INVALID_SNAPSHOT}:
        return SecurityDecisionCode.CONTEXT_INCOMPLETE
    return SecurityDecisionCode.PROVIDER_FAILURE
