from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from core.domain.common import normalize_utc, require_non_empty
from core.domain.errors import InvalidStateTransitionError, InvariantViolationError
from core.domain.identifiers import AuthorizationId, IncidentId


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentType(str, Enum):
    OPERATIONAL = "OPERATIONAL"
    AUDIT_GAP = "AUDIT_GAP"
    DATA_INTEGRITY = "DATA_INTEGRITY"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    RECOVERY_EXHAUSTED = "RECOVERY_EXHAUSTED"
    STALE_LEASE = "STALE_LEASE"
    UNAUTHORIZED_EXECUTION = "UNAUTHORIZED_EXECUTION"


class IncidentState(str, Enum):
    DETECTED = "DETECTED"
    TRIAGED = "TRIAGED"
    CONTAINED = "CONTAINED"
    REMEDIATED = "REMEDIATED"
    VERIFIED = "VERIFIED"
    AUTHORIZED_FOR_REACTIVATION = "AUTHORIZED_FOR_REACTIVATION"
    CLOSED = "CLOSED"


_SEVERITY_RANK = {
    IncidentSeverity.LOW: 0,
    IncidentSeverity.MEDIUM: 1,
    IncidentSeverity.HIGH: 2,
    IncidentSeverity.CRITICAL: 3,
}

MINIMUM_SEVERITY = {
    IncidentType.OPERATIONAL: IncidentSeverity.LOW,
    IncidentType.AUDIT_GAP: IncidentSeverity.MEDIUM,
    IncidentType.DATA_INTEGRITY: IncidentSeverity.HIGH,
    IncidentType.AUTHENTICATION_FAILURE: IncidentSeverity.HIGH,
    IncidentType.RECOVERY_EXHAUSTED: IncidentSeverity.HIGH,
    IncidentType.STALE_LEASE: IncidentSeverity.CRITICAL,
    IncidentType.UNAUTHORIZED_EXECUTION: IncidentSeverity.CRITICAL,
}

_STATE_ORDER = tuple(IncidentState)
_OPEN_STATES = frozenset(set(IncidentState) - {IncidentState.CLOSED})


@dataclass(frozen=True)
class Incident:
    incident_id: IncidentId
    incident_type: IncidentType
    severity: IncidentSeverity
    state: IncidentState
    detected_at: datetime
    updated_at: datetime
    reason: str
    parent_id: IncidentId | None = None
    ancestor_ids: tuple[IncidentId, ...] = ()
    remediator: str | None = None
    final_verifier: str | None = None
    self_reverification_complete: bool = False
    reactivation_authorization_id: AuthorizationId | None = None

    def __post_init__(self) -> None:
        detected = normalize_utc(self.detected_at, field_name="detected_at")
        updated = normalize_utc(self.updated_at, field_name="updated_at")
        if updated < detected:
            raise InvariantViolationError("incident update cannot precede detection")
        if _SEVERITY_RANK[self.severity] < _SEVERITY_RANK[MINIMUM_SEVERITY[self.incident_type]]:
            raise InvariantViolationError("incident severity is below its automatic minimum")
        if self.parent_id == self.incident_id or self.incident_id in self.ancestor_ids:
            raise InvariantViolationError("incident hierarchy cannot contain a cycle")
        if len(set(self.ancestor_ids)) != len(self.ancestor_ids):
            raise InvariantViolationError("incident ancestors must be unique")
        if self.parent_id is not None and (
            not self.ancestor_ids or self.ancestor_ids[-1] != self.parent_id
        ):
            raise InvariantViolationError("parent must be the final declared ancestor")
        object.__setattr__(self, "detected_at", detected)
        object.__setattr__(self, "updated_at", updated)
        object.__setattr__(self, "reason", require_non_empty(self.reason, field_name="reason"))
        state_index = _STATE_ORDER.index(self.state)
        if state_index >= _STATE_ORDER.index(IncidentState.REMEDIATED) and not self.remediator:
            raise InvariantViolationError("remediated incident requires a remediator")
        if state_index >= _STATE_ORDER.index(IncidentState.VERIFIED):
            if not self.final_verifier or self.final_verifier == self.remediator:
                raise InvariantViolationError("verified incident requires an independent final verifier")
            if not self.self_reverification_complete:
                raise InvariantViolationError("verified incident requires its own final reverification")
        if state_index >= _STATE_ORDER.index(IncidentState.AUTHORIZED_FOR_REACTIVATION):
            if self.reactivation_authorization_id is None:
                raise InvariantViolationError("reactivation state requires separate authorization")

    def escalate(self, severity: IncidentSeverity, *, changed_at: datetime) -> Incident:
        if _SEVERITY_RANK[severity] < _SEVERITY_RANK[self.severity]:
            raise InvalidStateTransitionError("automatic severity reduction is prohibited")
        return replace(self, severity=severity, updated_at=self._validated_change_time(changed_at))

    def _validated_change_time(self, changed_at: datetime) -> datetime:
        observed = normalize_utc(changed_at, field_name="changed_at")
        if observed < self.updated_at:
            raise InvalidStateTransitionError("incident change cannot precede its latest update")
        return observed

    def transition(
        self,
        next_state: IncidentState,
        *,
        changed_at: datetime,
        remediator: str | None = None,
        final_verifier: str | None = None,
        self_reverification_complete: bool | None = None,
        reactivation_authorization_id: AuthorizationId | None = None,
    ) -> Incident:
        return self._transition(
            next_state,
            changed_at=changed_at,
            remediator=remediator,
            final_verifier=final_verifier,
            self_reverification_complete=self_reverification_complete,
            reactivation_authorization_id=reactivation_authorization_id,
            hierarchy_validated=False,
        )

    def _transition(
        self,
        next_state: IncidentState,
        *,
        changed_at: datetime,
        remediator: str | None = None,
        final_verifier: str | None = None,
        self_reverification_complete: bool | None = None,
        reactivation_authorization_id: AuthorizationId | None = None,
        hierarchy_validated: bool,
    ) -> Incident:
        current_index = _STATE_ORDER.index(self.state)
        if current_index + 1 >= len(_STATE_ORDER) or _STATE_ORDER[current_index + 1] is not next_state:
            raise InvalidStateTransitionError("incident lifecycle transitions must be strictly sequential")
        if next_state is IncidentState.CLOSED and not hierarchy_validated:
            raise InvalidStateTransitionError("incident closure must be performed by IncidentHierarchy")
        updates: dict[str, object] = {
            "state": next_state,
            "updated_at": self._validated_change_time(changed_at),
        }
        if next_state is IncidentState.REMEDIATED:
            updates["remediator"] = require_non_empty(remediator or "", field_name="remediator")
        if next_state is IncidentState.VERIFIED:
            verifier = require_non_empty(final_verifier or "", field_name="final_verifier")
            if not self.remediator or verifier == self.remediator:
                raise InvariantViolationError("final verifier must differ from the remediator")
            if self_reverification_complete is not True:
                raise InvariantViolationError("incident requires its own final reverification")
            updates["final_verifier"] = verifier
            updates["self_reverification_complete"] = True
        if next_state is IncidentState.AUTHORIZED_FOR_REACTIVATION:
            if reactivation_authorization_id is None:
                raise InvariantViolationError("reactivation requires a separate authorization document")
            updates["reactivation_authorization_id"] = reactivation_authorization_id
        if next_state is IncidentState.CLOSED:
            if not self.self_reverification_complete or self.reactivation_authorization_id is None:
                raise InvariantViolationError("closure requires reverification and separate reactivation authorization")
        return replace(self, **updates)


@dataclass(frozen=True)
class IncidentHierarchy:
    incidents: tuple[Incident, ...]

    def __post_init__(self) -> None:
        by_id = {incident.incident_id: incident for incident in self.incidents}
        if len(by_id) != len(self.incidents):
            raise InvariantViolationError("incident ids must be unique")
        for incident in self.incidents:
            if incident.parent_id is not None and incident.parent_id not in by_id:
                raise InvariantViolationError("incident parent must exist in the hierarchy")
            lineage = []
            seen = {incident.incident_id}
            parent_id = incident.parent_id
            while parent_id is not None:
                if parent_id in seen:
                    raise InvariantViolationError("incident hierarchy cannot contain a cycle")
                seen.add(parent_id)
                lineage.append(parent_id)
                parent_id = by_id[parent_id].parent_id
            expected_ancestors = tuple(reversed(lineage))
            if incident.ancestor_ids != expected_ancestors:
                raise InvariantViolationError("declared incident ancestors do not match parent lineage")
        for incident in self.incidents:
            if incident.state is IncidentState.CLOSED and any(
                incident.incident_id in descendant.ancestor_ids
                and descendant.state in _OPEN_STATES
                for descendant in self.incidents
            ):
                raise InvariantViolationError("closed incident cannot contain an open descendant")

    def open_descendants(self, incident_id: IncidentId) -> tuple[IncidentId, ...]:
        self.incident(incident_id)
        descendants = []
        for incident in self.incidents:
            if incident_id in incident.ancestor_ids and incident.state in _OPEN_STATES:
                descendants.append(incident.incident_id)
        return tuple(sorted(descendants, key=str))

    def incident(self, incident_id: IncidentId) -> Incident:
        for incident in self.incidents:
            if incident.incident_id == incident_id:
                return incident
        raise InvariantViolationError("incident must exist in the hierarchy")

    def close(self, incident_id: IncidentId, *, changed_at: datetime) -> IncidentHierarchy:
        incident = self.incident(incident_id)
        if self.open_descendants(incident_id):
            raise InvariantViolationError("incident cannot close while a descendant remains open")
        closed = incident._transition(
            IncidentState.CLOSED,
            changed_at=changed_at,
            hierarchy_validated=True,
        )
        return replace(
            self,
            incidents=tuple(
                closed if item.incident_id == incident_id else item
                for item in self.incidents
            ),
        )
