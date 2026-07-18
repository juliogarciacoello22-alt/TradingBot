"""Immutable, deterministic security-context evidence contracts.

The models in this module describe evidence supplied by an external source.
They do not discover evidence, verify real-world authority, or authorize an
operation.
"""

from __future__ import annotations

import hmac
import json
import re
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from core.domain.common import normalize_utc, require_non_empty, require_sha256
from core.domain.errors import DomainContractError
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
from core.domain.serialization import canonical_json, canonical_sha256, to_canonical_data


SECURITY_CONTEXT_SCHEMA_VERSION = 1

_CONTEXT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class SecurityContextValidationError(DomainContractError):
    """The supplied context violates a structural invariant."""


class SecurityContextSerializationError(DomainContractError):
    """Serialized context data is malformed or non-canonical."""


class UnsupportedSecurityContextVersionError(SecurityContextSerializationError):
    """A serialized context uses an unsupported schema version."""


class EvidenceVerificationState(str, Enum):
    UNKNOWN = "UNKNOWN"
    NOT_VERIFIED = "NOT_VERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class ClockConfidence(str, Enum):
    UNKNOWN = "UNKNOWN"
    UNTRUSTED = "UNTRUSTED"
    TRUSTED = "TRUSTED"


class RecoveryActivity(str, Enum):
    UNKNOWN = "UNKNOWN"
    CLEAR = "CLEAR"
    RECOVERY_ACTIVE = "RECOVERY_ACTIVE"
    BACKFILL_ACTIVE = "BACKFILL_ACTIVE"


class SecurityEvidenceKind(str, Enum):
    SOURCE_IDENTITY = "SOURCE_IDENTITY"
    BOOT_IDENTITY = "BOOT_IDENTITY"
    AUTHORITY = "AUTHORITY"
    AUTHENTICATION = "AUTHENTICATION"
    HEARTBEAT = "HEARTBEAT"
    LEASE = "LEASE"
    FENCING = "FENCING"
    LOCK = "LOCK"
    CLOCK = "CLOCK"
    REVOCATION = "REVOCATION"
    RECOVERY = "RECOVERY"


@dataclass(frozen=True, order=True)
class ContextId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _CONTEXT_ID_PATTERN.fullmatch(self.value):
            raise SecurityContextValidationError(
                f"ContextId must match {_CONTEXT_ID_PATTERN.pattern}"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class EvidenceReference:
    kind: SecurityEvidenceKind
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SecurityEvidenceKind):
            raise SecurityContextValidationError("evidence kind is invalid")
        object.__setattr__(self, "sha256", require_sha256(self.sha256, field_name="sha256"))


@dataclass(frozen=True)
class VerificationEnvelope:
    state: EvidenceVerificationState
    evidence_hashes: tuple[str, ...] = ()
    verified_at_utc: datetime | None = None
    valid_until_utc: datetime | None = None
    verifier_id: str | None = None
    rejection_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceVerificationState):
            raise SecurityContextValidationError("verification state is invalid")
        hashes = tuple(
            sorted(
                {
                    require_sha256(item, field_name="evidence_hash")
                    for item in self.evidence_hashes
                }
            )
        )
        object.__setattr__(self, "evidence_hashes", hashes)

        verified_at = self.verified_at_utc
        valid_until = self.valid_until_utc
        if verified_at is not None:
            verified_at = normalize_utc(verified_at, field_name="verified_at_utc")
            object.__setattr__(self, "verified_at_utc", verified_at)
        if valid_until is not None:
            valid_until = normalize_utc(valid_until, field_name="valid_until_utc")
            object.__setattr__(self, "valid_until_utc", valid_until)
        if verified_at is not None and valid_until is not None and valid_until <= verified_at:
            raise SecurityContextValidationError("verification validity must end after assessment")

        verifier = self.verifier_id
        rejection = self.rejection_code
        if verifier is not None:
            verifier = require_non_empty(verifier, field_name="verifier_id")
            object.__setattr__(self, "verifier_id", verifier)
        if rejection is not None:
            rejection = require_non_empty(rejection, field_name="rejection_code")
            object.__setattr__(self, "rejection_code", rejection)

        if self.state is EvidenceVerificationState.VERIFIED:
            if not hashes or verified_at is None or verifier is None:
                raise SecurityContextValidationError(
                    "verified evidence requires hashes, assessment time, and verifier"
                )
            if rejection is not None:
                raise SecurityContextValidationError("verified evidence cannot have a rejection")
        elif self.state is EvidenceVerificationState.REJECTED:
            if verified_at is None or verifier is None or rejection is None:
                raise SecurityContextValidationError(
                    "rejected evidence requires assessment time, verifier, and rejection code"
                )
            if valid_until is not None:
                raise SecurityContextValidationError("rejected evidence cannot have validity")
        elif any(item is not None for item in (verified_at, valid_until, verifier, rejection)):
            raise SecurityContextValidationError(
                "unknown or unverified evidence cannot claim verification metadata"
            )


@dataclass(frozen=True)
class VerifiedSecurityLock:
    lock: SecurityLock
    verification: VerificationEnvelope

    def __post_init__(self) -> None:
        if not isinstance(self.lock, SecurityLock):
            raise SecurityContextValidationError("lock must be a SecurityLock")
        if self.lock.state is not LockState.LOCKED:
            raise SecurityContextValidationError("active_locks may contain only locked entries")
        if not isinstance(self.verification, VerificationEnvelope):
            raise SecurityContextValidationError("lock verification is invalid")


@dataclass(frozen=True)
class ClockEvidence:
    confidence: ClockConfidence
    observed_at_utc: datetime | None
    monotonic_ns: int | None
    verification: VerificationEnvelope

    def __post_init__(self) -> None:
        if not isinstance(self.confidence, ClockConfidence):
            raise SecurityContextValidationError("clock confidence is invalid")
        if self.observed_at_utc is not None:
            object.__setattr__(
                self,
                "observed_at_utc",
                normalize_utc(self.observed_at_utc, field_name="observed_at_utc"),
            )
        if self.monotonic_ns is not None and (
            isinstance(self.monotonic_ns, bool)
            or not isinstance(self.monotonic_ns, int)
            or self.monotonic_ns < 0
        ):
            raise SecurityContextValidationError("monotonic_ns must be a non-negative integer")
        if not isinstance(self.verification, VerificationEnvelope):
            raise SecurityContextValidationError("clock verification is invalid")
        if self.confidence is ClockConfidence.TRUSTED and (
            self.observed_at_utc is None
            or self.monotonic_ns is None
            or self.verification.state is not EvidenceVerificationState.VERIFIED
        ):
            raise SecurityContextValidationError(
                "trusted clock evidence requires UTC, monotonic, and verified evidence"
            )


@dataclass(frozen=True)
class RecoveryEvidence:
    activity: RecoveryActivity
    recovery_id: RecoveryId | None
    verification: VerificationEnvelope

    def __post_init__(self) -> None:
        if not isinstance(self.activity, RecoveryActivity):
            raise SecurityContextValidationError("recovery activity is invalid")
        if self.recovery_id is not None and not isinstance(self.recovery_id, RecoveryId):
            raise SecurityContextValidationError("recovery_id is invalid")
        if not isinstance(self.verification, VerificationEnvelope):
            raise SecurityContextValidationError("recovery verification is invalid")
        if self.activity in {RecoveryActivity.RECOVERY_ACTIVE, RecoveryActivity.BACKFILL_ACTIVE}:
            if self.recovery_id is None:
                raise SecurityContextValidationError("active recovery requires recovery_id")


@dataclass(frozen=True)
class SecurityContextSnapshot:
    schema_version: int
    context_id: ContextId
    generation: int
    overall_verification: EvidenceVerificationState
    source_identity: SourceIdentity | None
    source_verification: VerificationEnvelope
    boot_identity: BootIdentity | None
    boot_verification: VerificationEnvelope
    authority_assertion: AuthorityAssertion | None
    authority_verification: VerificationEnvelope
    authentication: AuthenticationRecord | None
    authentication_verification: VerificationEnvelope
    heartbeat: Heartbeat | None
    heartbeat_verification: VerificationEnvelope
    lease: Lease | None
    lease_verification: VerificationEnvelope
    fencing_token: FencingToken | None
    fencing_verification: VerificationEnvelope
    active_locks: tuple[VerifiedSecurityLock, ...]
    clock: ClockEvidence
    revocation_generation: int | None
    revocation_verification: VerificationEnvelope
    recovery: RecoveryEvidence
    evidence_references: tuple[EvidenceReference, ...]
    context_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int):
            raise SecurityContextValidationError("schema_version must be an integer")
        if self.schema_version != SECURITY_CONTEXT_SCHEMA_VERSION:
            raise UnsupportedSecurityContextVersionError(
                f"unsupported security context version: {self.schema_version}"
            )
        if not isinstance(self.context_id, ContextId):
            raise SecurityContextValidationError("context_id is invalid")
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation <= 0:
            raise SecurityContextValidationError("generation must be a positive integer")
        if not isinstance(self.overall_verification, EvidenceVerificationState):
            raise SecurityContextValidationError("overall verification is invalid")

        optional_components = (
            (self.source_identity, SourceIdentity, "source_identity"),
            (self.boot_identity, BootIdentity, "boot_identity"),
            (self.authority_assertion, AuthorityAssertion, "authority_assertion"),
            (self.authentication, AuthenticationRecord, "authentication"),
            (self.heartbeat, Heartbeat, "heartbeat"),
            (self.lease, Lease, "lease"),
        )
        for value, expected_type, field_name in optional_components:
            if value is not None and not isinstance(value, expected_type):
                raise SecurityContextValidationError(f"{field_name} is invalid")

        envelope_fields = (
            self.source_verification,
            self.boot_verification,
            self.authority_verification,
            self.authentication_verification,
            self.heartbeat_verification,
            self.lease_verification,
            self.fencing_verification,
            self.revocation_verification,
        )
        if not all(isinstance(item, VerificationEnvelope) for item in envelope_fields):
            raise SecurityContextValidationError("component verification is invalid")
        if self.fencing_token is not None and not isinstance(self.fencing_token, FencingToken):
            raise SecurityContextValidationError("fencing_token is invalid")
        if self.revocation_generation is not None and (
            isinstance(self.revocation_generation, bool)
            or not isinstance(self.revocation_generation, int)
            or self.revocation_generation < 0
        ):
            raise SecurityContextValidationError(
                "revocation_generation must be a non-negative integer"
            )
        if not isinstance(self.clock, ClockEvidence):
            raise SecurityContextValidationError("clock evidence is invalid")
        if not isinstance(self.recovery, RecoveryEvidence):
            raise SecurityContextValidationError("recovery evidence is invalid")

        if not isinstance(self.active_locks, tuple) or not all(
            isinstance(item, VerifiedSecurityLock) for item in self.active_locks
        ):
            raise SecurityContextValidationError("active_locks contains an invalid value")
        locks = tuple(sorted(self.active_locks, key=lambda item: item.lock.event_id.value))
        lock_ids = tuple(item.lock.event_id for item in locks)
        if len(set(lock_ids)) != len(lock_ids):
            raise SecurityContextValidationError("active lock event ids must be unique")
        object.__setattr__(self, "active_locks", locks)

        if not isinstance(self.evidence_references, tuple) or not all(
            isinstance(item, EvidenceReference) for item in self.evidence_references
        ):
            raise SecurityContextValidationError("evidence_references contains an invalid value")
        references = tuple(
            sorted(self.evidence_references, key=lambda item: (item.kind.value, item.sha256))
        )
        reference_keys = tuple((item.kind, item.sha256) for item in references)
        if len(set(reference_keys)) != len(reference_keys):
            raise SecurityContextValidationError("evidence references must be unique")
        object.__setattr__(self, "evidence_references", references)
        object.__setattr__(
            self,
            "context_hash",
            canonical_sha256(_to_context_canonical_data(self._content_payload())),
        )

    def _content_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "context_id": self.context_id,
            "generation": self.generation,
            "overall_verification": self.overall_verification,
            "source_identity": self.source_identity,
            "source_verification": self.source_verification,
            "boot_identity": self.boot_identity,
            "boot_verification": self.boot_verification,
            "authority_assertion": self.authority_assertion,
            "authority_verification": self.authority_verification,
            "authentication": self.authentication,
            "authentication_verification": self.authentication_verification,
            "heartbeat": self.heartbeat,
            "heartbeat_verification": self.heartbeat_verification,
            "lease": self.lease,
            "lease_verification": self.lease_verification,
            "fencing_token": self.fencing_token,
            "fencing_verification": self.fencing_verification,
            "active_locks": self.active_locks,
            "clock": self.clock,
            "revocation_generation": self.revocation_generation,
            "revocation_verification": self.revocation_verification,
            "recovery": self.recovery,
            "evidence_references": self.evidence_references,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = _to_context_canonical_data(self._content_payload())
        payload["context_hash"] = self.context_hash
        return payload

    def to_json(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SecurityContextSnapshot:
        data = _require_mapping(value, field_name="security_context")
        _require_keys(data, set(_SNAPSHOT_KEYS), field_name="security_context")
        version = _schema_version_value(data["schema_version"])

        snapshot = cls(
            schema_version=version,
            context_id=ContextId(_identifier_value(data["context_id"], "context_id")),
            generation=_require_int(data["generation"], field_name="generation", minimum=1),
            overall_verification=_enum_value(
                EvidenceVerificationState,
                data["overall_verification"],
                "overall_verification",
            ),
            source_identity=_source_identity(data["source_identity"]),
            source_verification=_verification(data["source_verification"]),
            boot_identity=_boot_identity(data["boot_identity"]),
            boot_verification=_verification(data["boot_verification"]),
            authority_assertion=_authority(data["authority_assertion"]),
            authority_verification=_verification(data["authority_verification"]),
            authentication=_authentication(data["authentication"]),
            authentication_verification=_verification(data["authentication_verification"]),
            heartbeat=_heartbeat(data["heartbeat"]),
            heartbeat_verification=_verification(data["heartbeat_verification"]),
            lease=_lease(data["lease"]),
            lease_verification=_verification(data["lease_verification"]),
            fencing_token=_fencing_token(data["fencing_token"]),
            fencing_verification=_verification(data["fencing_verification"]),
            active_locks=tuple(_verified_lock(item) for item in _require_list(data["active_locks"], "active_locks")),
            clock=_clock(data["clock"]),
            revocation_generation=_optional_int(
                data["revocation_generation"],
                field_name="revocation_generation",
                minimum=0,
            ),
            revocation_verification=_verification(data["revocation_verification"]),
            recovery=_recovery(data["recovery"]),
            evidence_references=tuple(
                _evidence_reference(item)
                for item in _require_list(data["evidence_references"], "evidence_references")
            ),
        )
        supplied_hash = require_sha256(data["context_hash"], field_name="context_hash")
        if not hmac.compare_digest(snapshot.context_hash, supplied_hash):
            raise SecurityContextSerializationError("security context hash mismatch")
        return snapshot

    @classmethod
    def from_json(cls, value: str) -> SecurityContextSnapshot:
        if not isinstance(value, str):
            raise SecurityContextSerializationError("serialized context must be a string")
        try:
            data = json.loads(value, object_pairs_hook=_unique_object)
        except (TypeError, ValueError) as exc:
            raise SecurityContextSerializationError("invalid security context JSON") from exc
        return cls.from_dict(data)


_SNAPSHOT_KEYS = (
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


_SCALAR_VALUE_WRAPPERS = (
    ContextId,
    EventId,
    RecoveryId,
    SourceId,
    BootId,
    LeaseId,
    FencingToken,
)


def _to_context_canonical_data(value: Any) -> Any:
    if isinstance(value, _SCALAR_VALUE_WRAPPERS):
        return value.value
    if isinstance(value, Enum):
        return _to_context_canonical_data(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _to_context_canonical_data(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            key: _to_context_canonical_data(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_to_context_canonical_data(item) for item in value]
    return to_canonical_data(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise SecurityContextSerializationError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _require_mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SecurityContextSerializationError(f"{field_name} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise SecurityContextSerializationError(f"{field_name} keys must be strings")
    return value


def _require_keys(value: Mapping[str, Any], expected: set[str], *, field_name: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise SecurityContextSerializationError(
            f"{field_name} fields mismatch; missing={missing}, extra={extra}"
        )


def _require_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise SecurityContextSerializationError(f"{field_name} must be an array")
    return value


def _require_int(value: Any, *, field_name: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise SecurityContextSerializationError(f"{field_name} must be an integer >= {minimum}")
    return value


def _schema_version_value(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SecurityContextValidationError("schema_version must be an integer")
    if value != SECURITY_CONTEXT_SCHEMA_VERSION:
        raise UnsupportedSecurityContextVersionError(
            f"unsupported security context version: {value}"
        )
    return value


def _optional_int(value: Any, *, field_name: str, minimum: int) -> int | None:
    if value is None:
        return None
    return _require_int(value, field_name=field_name, minimum=minimum)


def _identifier_value(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise SecurityContextSerializationError(
            f"{field_name} must be a canonical identifier string"
        )
    return value


def _enum_value(enum_type: type[Enum], value: Any, field_name: str) -> Any:
    if not isinstance(value, str):
        raise SecurityContextSerializationError(f"{field_name} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise SecurityContextSerializationError(f"{field_name} is invalid") from exc


def _datetime_value(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise SecurityContextSerializationError(f"{field_name} must be a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SecurityContextSerializationError(f"{field_name} is invalid") from exc
    return normalize_utc(parsed, field_name=field_name)


def _optional_datetime(value: Any, field_name: str) -> datetime | None:
    return None if value is None else _datetime_value(value, field_name)


def _verification(value: Any) -> VerificationEnvelope:
    data = _require_mapping(value, field_name="verification")
    _require_keys(
        data,
        {
            "state",
            "evidence_hashes",
            "verified_at_utc",
            "valid_until_utc",
            "verifier_id",
            "rejection_code",
        },
        field_name="verification",
    )
    return VerificationEnvelope(
        state=_enum_value(EvidenceVerificationState, data["state"], "verification.state"),
        evidence_hashes=tuple(_require_list(data["evidence_hashes"], "evidence_hashes")),
        verified_at_utc=_optional_datetime(data["verified_at_utc"], "verified_at_utc"),
        valid_until_utc=_optional_datetime(data["valid_until_utc"], "valid_until_utc"),
        verifier_id=data["verifier_id"],
        rejection_code=data["rejection_code"],
    )


def _source_identity(value: Any) -> SourceIdentity | None:
    if value is None:
        return None
    data = _require_mapping(value, field_name="source_identity")
    _require_keys(data, {"source_id", "principal"}, field_name="source_identity")
    return SourceIdentity(
        source_id=SourceId(_identifier_value(data["source_id"], "source_id")),
        principal=data["principal"],
    )


def _boot_identity(value: Any) -> BootIdentity | None:
    if value is None:
        return None
    data = _require_mapping(value, field_name="boot_identity")
    _require_keys(data, {"boot_id", "source_id", "started_at"}, field_name="boot_identity")
    return BootIdentity(
        boot_id=BootId(_identifier_value(data["boot_id"], "boot_id")),
        source_id=SourceId(_identifier_value(data["source_id"], "source_id")),
        started_at=_datetime_value(data["started_at"], "started_at"),
    )


def _authority(value: Any) -> AuthorityAssertion | None:
    if value is None:
        return None
    data = _require_mapping(value, field_name="authority_assertion")
    _require_keys(
        data,
        {"actor", "role", "asserted_at", "evidence_hashes", "verified"},
        field_name="authority_assertion",
    )
    verified = data["verified"]
    if not isinstance(verified, bool):
        raise SecurityContextSerializationError("authority.verified must be bool")
    return AuthorityAssertion(
        actor=data["actor"],
        role=_enum_value(AuthorityRole, data["role"], "authority.role"),
        asserted_at=_datetime_value(data["asserted_at"], "asserted_at"),
        evidence_hashes=tuple(_require_list(data["evidence_hashes"], "evidence_hashes")),
        verified=verified,
    )


def _authentication(value: Any) -> AuthenticationRecord | None:
    if value is None:
        return None
    data = _require_mapping(value, field_name="authentication")
    _require_keys(
        data,
        {"source_id", "boot_id", "state", "assessed_at", "mechanism", "evidence_hashes"},
        field_name="authentication",
    )
    return AuthenticationRecord(
        source_id=SourceId(_identifier_value(data["source_id"], "source_id")),
        boot_id=BootId(_identifier_value(data["boot_id"], "boot_id")),
        state=_enum_value(AuthenticationState, data["state"], "authentication.state"),
        assessed_at=_datetime_value(data["assessed_at"], "assessed_at"),
        mechanism=data["mechanism"],
        evidence_hashes=tuple(_require_list(data["evidence_hashes"], "evidence_hashes")),
    )


def _fencing_token(value: Any) -> FencingToken | None:
    if value is None:
        return None
    return FencingToken(
        _require_int(value, field_name="fencing_token", minimum=1)
    )


def _required_fencing_token(value: Any) -> FencingToken:
    token = _fencing_token(value)
    if token is None:
        raise SecurityContextSerializationError("fencing_token is required")
    return token


def _heartbeat(value: Any) -> Heartbeat | None:
    if value is None:
        return None
    data = _require_mapping(value, field_name="heartbeat")
    _require_keys(
        data,
        {"event_id", "source_id", "boot_id", "fencing_token", "sequence", "observed_at"},
        field_name="heartbeat",
    )
    return Heartbeat(
        event_id=EventId(_identifier_value(data["event_id"], "event_id")),
        source_id=SourceId(_identifier_value(data["source_id"], "source_id")),
        boot_id=BootId(_identifier_value(data["boot_id"], "boot_id")),
        fencing_token=_required_fencing_token(data["fencing_token"]),
        sequence=_require_int(data["sequence"], field_name="sequence", minimum=1),
        observed_at=_datetime_value(data["observed_at"], "observed_at"),
    )


def _lease(value: Any) -> Lease | None:
    if value is None:
        return None
    data = _require_mapping(value, field_name="lease")
    _require_keys(
        data,
        {"lease_id", "source_id", "boot_id", "fencing_token", "issued_at", "expires_at", "state"},
        field_name="lease",
    )
    return Lease(
        lease_id=LeaseId(_identifier_value(data["lease_id"], "lease_id")),
        source_id=SourceId(_identifier_value(data["source_id"], "source_id")),
        boot_id=BootId(_identifier_value(data["boot_id"], "boot_id")),
        fencing_token=_required_fencing_token(data["fencing_token"]),
        issued_at=_datetime_value(data["issued_at"], "issued_at"),
        expires_at=_datetime_value(data["expires_at"], "expires_at"),
        state=_enum_value(LeaseState, data["state"], "lease.state"),
    )


def _verified_lock(value: Any) -> VerifiedSecurityLock:
    data = _require_mapping(value, field_name="verified_lock")
    _require_keys(data, {"lock", "verification"}, field_name="verified_lock")
    lock_data = _require_mapping(data["lock"], field_name="lock")
    _require_keys(lock_data, {"event_id", "state", "changed_at", "reason"}, field_name="lock")
    return VerifiedSecurityLock(
        lock=SecurityLock(
            event_id=EventId(_identifier_value(lock_data["event_id"], "event_id")),
            state=_enum_value(LockState, lock_data["state"], "lock.state"),
            changed_at=_datetime_value(lock_data["changed_at"], "changed_at"),
            reason=lock_data["reason"],
        ),
        verification=_verification(data["verification"]),
    )


def _clock(value: Any) -> ClockEvidence:
    data = _require_mapping(value, field_name="clock")
    _require_keys(data, {"confidence", "observed_at_utc", "monotonic_ns", "verification"}, field_name="clock")
    return ClockEvidence(
        confidence=_enum_value(ClockConfidence, data["confidence"], "clock.confidence"),
        observed_at_utc=_optional_datetime(data["observed_at_utc"], "observed_at_utc"),
        monotonic_ns=_optional_int(data["monotonic_ns"], field_name="monotonic_ns", minimum=0),
        verification=_verification(data["verification"]),
    )


def _recovery(value: Any) -> RecoveryEvidence:
    data = _require_mapping(value, field_name="recovery")
    _require_keys(data, {"activity", "recovery_id", "verification"}, field_name="recovery")
    recovery_id = data["recovery_id"]
    return RecoveryEvidence(
        activity=_enum_value(RecoveryActivity, data["activity"], "recovery.activity"),
        recovery_id=None if recovery_id is None else RecoveryId(_identifier_value(recovery_id, "recovery_id")),
        verification=_verification(data["verification"]),
    )


def _evidence_reference(value: Any) -> EvidenceReference:
    data = _require_mapping(value, field_name="evidence_reference")
    _require_keys(data, {"kind", "sha256"}, field_name="evidence_reference")
    return EvidenceReference(
        kind=_enum_value(SecurityEvidenceKind, data["kind"], "evidence.kind"),
        sha256=data["sha256"],
    )
