from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from core.domain.common import normalize_utc, require_non_empty, require_sha256
from core.domain.errors import InvariantViolationError
from core.domain.identifiers import EventId
from core.domain.serialization import canonical_sha256


class AuditEventType(str, Enum):
    CONTRACT_CREATED = "CONTRACT_CREATED"
    STATE_TRANSITION = "STATE_TRANSITION"
    SECURITY_DECISION = "SECURITY_DECISION"
    INCIDENT_ACTION = "INCIDENT_ACTION"
    RECOVERY_ACTION = "RECOVERY_ACTION"
    CORRECTION = "CORRECTION"


@dataclass(frozen=True)
class AuditActor:
    actor_id: str
    actor_type: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_id", require_non_empty(self.actor_id, field_name="actor_id"))
        object.__setattr__(self, "actor_type", require_non_empty(self.actor_type, field_name="actor_type"))


@dataclass(frozen=True)
class AuditEvidence:
    evidence_type: str
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_type",
            require_non_empty(self.evidence_type, field_name="evidence_type"),
        )
        object.__setattr__(self, "sha256", require_sha256(self.sha256, field_name="sha256"))


@dataclass(frozen=True)
class AuditEvent:
    event_id: EventId
    event_type: AuditEventType
    occurred_at: datetime
    actor: AuditActor
    reason: str
    subject_id: str
    payload_hash: str
    evidence: tuple[AuditEvidence, ...] = ()
    previous_event_hash: str | None = None
    corrects_event_id: EventId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", normalize_utc(self.occurred_at, field_name="occurred_at"))
        object.__setattr__(self, "reason", require_non_empty(self.reason, field_name="reason"))
        object.__setattr__(self, "subject_id", require_non_empty(self.subject_id, field_name="subject_id"))
        object.__setattr__(self, "payload_hash", require_sha256(self.payload_hash, field_name="payload_hash"))
        if self.previous_event_hash is not None:
            object.__setattr__(
                self,
                "previous_event_hash",
                require_sha256(self.previous_event_hash, field_name="previous_event_hash"),
            )
        if self.event_type is AuditEventType.CORRECTION:
            if self.corrects_event_id is None or self.previous_event_hash is None:
                raise InvariantViolationError("correction events must link to the corrected event and hash")
        elif self.corrects_event_id is not None:
            raise InvariantViolationError("only correction events may identify a corrected event")

    @property
    def event_hash(self) -> str:
        return canonical_sha256(self)

    def correction(
        self,
        *,
        event_id: EventId,
        occurred_at: datetime,
        actor: AuditActor,
        reason: str,
        payload_hash: str,
        evidence: tuple[AuditEvidence, ...] = (),
    ) -> AuditEvent:
        observed = normalize_utc(occurred_at, field_name="occurred_at")
        if observed < self.occurred_at:
            raise InvariantViolationError("correction cannot precede the original audit event")
        return AuditEvent(
            event_id=event_id,
            event_type=AuditEventType.CORRECTION,
            occurred_at=observed,
            actor=actor,
            reason=reason,
            subject_id=self.subject_id,
            payload_hash=payload_hash,
            evidence=evidence,
            previous_event_hash=self.event_hash,
            corrects_event_id=self.event_id,
        )
