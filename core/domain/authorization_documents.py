from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from core.domain.common import normalize_utc, require_non_empty, require_sha256
from core.domain.errors import InvalidStateTransitionError, InvariantViolationError
from core.domain.identifiers import AuthorizationId, EventId, IncidentId


class AuthorizationDocumentState(str, Enum):
    ISSUED = "ISSUED"
    VERIFIED = "VERIFIED"
    CONSUMED = "CONSUMED"
    REVOKED = "REVOKED"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"


class IncidentAuthorizationScope(str, Enum):
    CONTAINMENT = "CONTAINMENT"
    REMEDIATION = "REMEDIATION"
    REACTIVATION = "REACTIVATION"


@dataclass(frozen=True)
class AuthorizationCondition:
    name: str
    expected_value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", require_non_empty(self.name, field_name="condition name"))
        object.__setattr__(
            self,
            "expected_value",
            require_non_empty(self.expected_value, field_name="expected value"),
        )


@dataclass(frozen=True)
class IncidentAuthorizationDocument:
    authorization_id: AuthorizationId
    incident_id: IncidentId
    issued_at: datetime
    expires_at: datetime
    issuer: str
    final_authority: str
    scopes: tuple[IncidentAuthorizationScope, ...]
    conditions: tuple[AuthorizationCondition, ...]
    resolution: str
    document_hash: str
    evidence_hashes: tuple[str, ...]
    state: AuthorizationDocumentState = AuthorizationDocumentState.ISSUED
    signature_verified: bool = False
    final_authority_verified: bool = False
    verified_at: datetime | None = None
    verification_hash: str | None = None
    consumed_at: datetime | None = None
    consumption_event_id: EventId | None = None

    def __post_init__(self) -> None:
        issued = normalize_utc(self.issued_at, field_name="issued_at")
        expires = normalize_utc(self.expires_at, field_name="expires_at")
        if expires <= issued:
            raise InvariantViolationError("authorization expiry must be after issue time")
        if not self.scopes or len(set(self.scopes)) != len(self.scopes):
            raise InvariantViolationError("authorization scopes must be non-empty and unique")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "issuer", require_non_empty(self.issuer, field_name="issuer"))
        object.__setattr__(
            self,
            "final_authority",
            require_non_empty(self.final_authority, field_name="final_authority"),
        )
        object.__setattr__(self, "resolution", require_non_empty(self.resolution, field_name="resolution"))
        object.__setattr__(self, "document_hash", require_sha256(self.document_hash, field_name="document_hash"))
        object.__setattr__(
            self,
            "evidence_hashes",
            tuple(require_sha256(item, field_name="evidence_hash") for item in self.evidence_hashes),
        )
        if self.verified_at is not None:
            object.__setattr__(self, "verified_at", normalize_utc(self.verified_at, field_name="verified_at"))
        if self.verification_hash is not None:
            object.__setattr__(
                self,
                "verification_hash",
                require_sha256(self.verification_hash, field_name="verification_hash"),
            )
        if self.consumed_at is not None:
            object.__setattr__(self, "consumed_at", normalize_utc(self.consumed_at, field_name="consumed_at"))
        if self.state in {
            AuthorizationDocumentState.VERIFIED,
            AuthorizationDocumentState.CONSUMED,
        }:
            if not self.signature_verified or not self.final_authority_verified:
                raise InvariantViolationError("verified authorization requires verified signature and final authority")
            if self.verified_at is None or self.verification_hash is None:
                raise InvariantViolationError("verified authorization requires verification evidence")
        if self.state is AuthorizationDocumentState.CONSUMED:
            if self.consumed_at is None or self.consumption_event_id is None:
                raise InvariantViolationError("consumed authorization requires consumption evidence")
            if self.consumed_at < self.verified_at or self.consumed_at >= self.expires_at:
                raise InvariantViolationError("consumption must follow verification and precede expiry")
        elif self.consumed_at is not None or self.consumption_event_id is not None:
            raise InvariantViolationError("only consumed authorization may contain consumption evidence")

    def verify(
        self,
        *,
        verified_at: datetime,
        signature_verified: bool,
        final_authority_verified: bool,
        verification_hash: str,
    ) -> IncidentAuthorizationDocument:
        if self.state is not AuthorizationDocumentState.ISSUED:
            raise InvalidStateTransitionError("only an issued authorization can be verified")
        observed = normalize_utc(verified_at, field_name="verified_at")
        state = AuthorizationDocumentState.VERIFIED
        if observed >= self.expires_at:
            state = AuthorizationDocumentState.EXPIRED
        elif not signature_verified or not final_authority_verified:
            state = AuthorizationDocumentState.INVALID
        return replace(
            self,
            state=state,
            signature_verified=signature_verified,
            final_authority_verified=final_authority_verified,
            verified_at=observed,
            verification_hash=require_sha256(verification_hash, field_name="verification_hash"),
        )

    def consume(
        self,
        *,
        consumed_at: datetime,
        scope: IncidentAuthorizationScope,
        conditions_satisfied: bool,
        consumption_event_id: EventId,
    ) -> IncidentAuthorizationDocument:
        if self.state is not AuthorizationDocumentState.VERIFIED:
            raise InvalidStateTransitionError("only a verified authorization can be consumed")
        observed = normalize_utc(consumed_at, field_name="consumed_at")
        if observed >= self.expires_at:
            return replace(self, state=AuthorizationDocumentState.EXPIRED)
        if scope not in self.scopes or not conditions_satisfied:
            return replace(self, state=AuthorizationDocumentState.INVALID)
        return replace(
            self,
            state=AuthorizationDocumentState.CONSUMED,
            consumed_at=observed,
            consumption_event_id=consumption_event_id,
        )

    def revoke(self) -> IncidentAuthorizationDocument:
        if self.state in {
            AuthorizationDocumentState.CONSUMED,
            AuthorizationDocumentState.REVOKED,
            AuthorizationDocumentState.INVALID,
            AuthorizationDocumentState.EXPIRED,
        }:
            raise InvalidStateTransitionError("authorization cannot be revoked from its current state")
        return replace(self, state=AuthorizationDocumentState.REVOKED)
