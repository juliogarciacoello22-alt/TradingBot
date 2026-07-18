from datetime import datetime, timedelta, timezone

import pytest

from core.domain.errors import InvalidStateTransitionError, InvariantViolationError
from core.domain.identifiers import AuthorizationId, IncidentId
from core.domain.incidents import (
    Incident,
    IncidentHierarchy,
    IncidentSeverity,
    IncidentState,
    IncidentType,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_incident(**overrides):
    values = {
        "incident_id": IncidentId("incident-1"),
        "incident_type": IncidentType.DATA_INTEGRITY,
        "severity": IncidentSeverity.HIGH,
        "state": IncidentState.DETECTED,
        "detected_at": NOW,
        "updated_at": NOW,
        "reason": "conflicting native bar",
    }
    values.update(overrides)
    return Incident(**values)


def advance_to_authorized(incident):
    incident = incident.transition(IncidentState.TRIAGED, changed_at=NOW + timedelta(minutes=1))
    incident = incident.transition(IncidentState.CONTAINED, changed_at=NOW + timedelta(minutes=2))
    incident = incident.transition(
        IncidentState.REMEDIATED,
        changed_at=NOW + timedelta(minutes=3),
        remediator="operator-a",
    )
    incident = incident.transition(
        IncidentState.VERIFIED,
        changed_at=NOW + timedelta(minutes=4),
        final_verifier="verifier-b",
        self_reverification_complete=True,
    )
    return incident.transition(
        IncidentState.AUTHORIZED_FOR_REACTIVATION,
        changed_at=NOW + timedelta(minutes=5),
        reactivation_authorization_id=AuthorizationId("auth-1"),
    )


def test_incident_severity_cannot_be_below_minimum_or_reduced():
    with pytest.raises(InvariantViolationError):
        make_incident(severity=IncidentSeverity.MEDIUM)
    incident = make_incident().escalate(IncidentSeverity.CRITICAL, changed_at=NOW)
    with pytest.raises(InvalidStateTransitionError):
        incident.escalate(IncidentSeverity.HIGH, changed_at=NOW)


def test_incident_lifecycle_is_strict_and_roles_are_separated():
    incident = make_incident()
    with pytest.raises(InvalidStateTransitionError):
        incident.transition(IncidentState.CONTAINED, changed_at=NOW)
    incident = incident.transition(IncidentState.TRIAGED, changed_at=NOW)
    incident = incident.transition(IncidentState.CONTAINED, changed_at=NOW)
    incident = incident.transition(IncidentState.REMEDIATED, changed_at=NOW, remediator="same")
    with pytest.raises(InvariantViolationError):
        incident.transition(
            IncidentState.VERIFIED,
            changed_at=NOW,
            final_verifier="same",
            self_reverification_complete=True,
        )


def test_parent_cannot_close_while_a_descendant_is_open():
    parent = advance_to_authorized(make_incident())
    child = make_incident(
        incident_id=IncidentId("incident-child"),
        parent_id=parent.incident_id,
        ancestor_ids=(parent.incident_id,),
    )
    hierarchy = IncidentHierarchy((parent, child))
    open_children = hierarchy.open_descendants(parent.incident_id)
    assert open_children == (child.incident_id,)
    with pytest.raises(InvariantViolationError):
        hierarchy.close(parent.incident_id, changed_at=NOW + timedelta(minutes=6))


def test_incident_cannot_bypass_hierarchy_for_closure():
    incident = advance_to_authorized(make_incident())
    with pytest.raises(InvalidStateTransitionError):
        incident.transition(IncidentState.CLOSED, changed_at=NOW + timedelta(minutes=6))


def test_closing_child_does_not_close_parent_and_parent_closes_separately():
    parent = advance_to_authorized(make_incident())
    child = advance_to_authorized(
        make_incident(
            incident_id=IncidentId("incident-child"),
            parent_id=parent.incident_id,
            ancestor_ids=(parent.incident_id,),
        )
    )
    hierarchy = IncidentHierarchy((parent, child))
    after_child = hierarchy.close(child.incident_id, changed_at=NOW + timedelta(minutes=6))
    assert after_child.incident(child.incident_id).state is IncidentState.CLOSED
    assert after_child.incident(parent.incident_id).state is IncidentState.AUTHORIZED_FOR_REACTIVATION
    after_parent = after_child.close(parent.incident_id, changed_at=NOW + timedelta(minutes=7))
    assert after_parent.incident(parent.incident_id).state is IncidentState.CLOSED


def test_hierarchy_rejects_preclosed_parent_with_open_descendant():
    parent = advance_to_authorized(make_incident())
    closed_parent = IncidentHierarchy((parent,)).close(
        parent.incident_id,
        changed_at=NOW + timedelta(minutes=6),
    ).incident(parent.incident_id)
    child = make_incident(
        incident_id=IncidentId("incident-child"),
        parent_id=parent.incident_id,
        ancestor_ids=(parent.incident_id,),
    )
    with pytest.raises(InvariantViolationError):
        IncidentHierarchy((closed_parent, child))


def test_incident_hierarchy_rejects_cycles():
    with pytest.raises(InvariantViolationError):
        make_incident(parent_id=IncidentId("incident-1"), ancestor_ids=(IncidentId("incident-1"),))


def test_hierarchy_detects_multi_incident_parent_cycle():
    first = make_incident(
        incident_id=IncidentId("incident-a"),
        parent_id=IncidentId("incident-b"),
        ancestor_ids=(IncidentId("incident-b"),),
    )
    second = make_incident(
        incident_id=IncidentId("incident-b"),
        parent_id=IncidentId("incident-a"),
        ancestor_ids=(IncidentId("incident-a"),),
    )
    with pytest.raises(InvariantViolationError):
        IncidentHierarchy((first, second))


def test_incident_transition_allows_equal_and_later_timestamps():
    incident = make_incident().transition(IncidentState.TRIAGED, changed_at=NOW)
    assert incident.updated_at == NOW
    later = incident.transition(IncidentState.CONTAINED, changed_at=NOW + timedelta(minutes=2))
    assert later.updated_at == NOW + timedelta(minutes=2)


def test_incident_transition_rejects_time_before_latest_update():
    incident = make_incident().transition(
        IncidentState.TRIAGED,
        changed_at=NOW + timedelta(minutes=2),
    )
    with pytest.raises(InvalidStateTransitionError):
        incident.transition(IncidentState.CONTAINED, changed_at=NOW + timedelta(minutes=1))
    with pytest.raises(InvalidStateTransitionError):
        incident.escalate(IncidentSeverity.CRITICAL, changed_at=NOW + timedelta(minutes=1))
