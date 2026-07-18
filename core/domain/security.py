from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from core.domain.common import normalize_utc, require_non_empty, require_sha256
from core.domain.errors import InvariantViolationError
from core.domain.identifiers import BootId, EventId, FencingToken, LeaseId, SourceId


class AuthorityRole(str, Enum):
    SOURCE_OPERATOR = "SOURCE_OPERATOR"
    SECURITY_CONTROLLER = "SECURITY_CONTROLLER"
    INCIDENT_COMMANDER = "INCIDENT_COMMANDER"
    FINAL_AUTHORITY = "FINAL_AUTHORITY"


class AuthenticationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class LeaseState(str, Enum):
    ISSUED = "ISSUED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    RELEASED = "RELEASED"


class LockState(str, Enum):
    LOCKED = "LOCKED"
    UNLOCKED = "UNLOCKED"


@dataclass(frozen=True)
class SourceIdentity:
    source_id: SourceId
    principal: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "principal", require_non_empty(self.principal, field_name="principal"))


@dataclass(frozen=True)
class BootIdentity:
    boot_id: BootId
    source_id: SourceId
    started_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "started_at", normalize_utc(self.started_at, field_name="started_at"))


@dataclass(frozen=True)
class AuthorityAssertion:
    actor: str
    role: AuthorityRole
    asserted_at: datetime
    evidence_hashes: tuple[str, ...]
    verified: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor", require_non_empty(self.actor, field_name="actor"))
        object.__setattr__(self, "asserted_at", normalize_utc(self.asserted_at, field_name="asserted_at"))
        hashes = tuple(require_sha256(item, field_name="evidence_hash") for item in self.evidence_hashes)
        if self.verified and not hashes:
            raise InvariantViolationError("verified authority requires evidence")
        object.__setattr__(self, "evidence_hashes", hashes)


@dataclass(frozen=True)
class AuthenticationRecord:
    source_id: SourceId
    boot_id: BootId
    state: AuthenticationState
    assessed_at: datetime
    mechanism: str
    evidence_hashes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessed_at", normalize_utc(self.assessed_at, field_name="assessed_at"))
        object.__setattr__(self, "mechanism", require_non_empty(self.mechanism, field_name="mechanism"))
        hashes = tuple(require_sha256(item, field_name="evidence_hash") for item in self.evidence_hashes)
        if self.state is AuthenticationState.VERIFIED and not hashes:
            raise InvariantViolationError("verified authentication requires evidence")
        object.__setattr__(self, "evidence_hashes", hashes)


@dataclass(frozen=True)
class Heartbeat:
    event_id: EventId
    source_id: SourceId
    boot_id: BootId
    fencing_token: FencingToken
    sequence: int
    observed_at: datetime

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise InvariantViolationError("heartbeat sequence must be positive")
        object.__setattr__(self, "observed_at", normalize_utc(self.observed_at, field_name="observed_at"))


@dataclass(frozen=True)
class Lease:
    lease_id: LeaseId
    source_id: SourceId
    boot_id: BootId
    fencing_token: FencingToken
    issued_at: datetime
    expires_at: datetime
    state: LeaseState

    def __post_init__(self) -> None:
        issued = normalize_utc(self.issued_at, field_name="issued_at")
        expires = normalize_utc(self.expires_at, field_name="expires_at")
        if expires <= issued:
            raise InvariantViolationError("lease expiry must be after issue time")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

    def is_valid_at(self, observed_at: datetime) -> bool:
        observed = normalize_utc(observed_at, field_name="observed_at")
        return self.state is LeaseState.ACTIVE and self.issued_at <= observed < self.expires_at


@dataclass(frozen=True)
class SecurityLock:
    event_id: EventId
    state: LockState
    changed_at: datetime
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed_at", normalize_utc(self.changed_at, field_name="changed_at"))
        object.__setattr__(self, "reason", require_non_empty(self.reason, field_name="reason"))
