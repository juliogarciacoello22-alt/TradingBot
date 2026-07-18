from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from core.domain.audit_events import (
    AuditActor,
    AuditEvent,
    AuditEventType,
    AuditEvidence,
)
from core.domain.errors import InvariantViolationError
from core.domain.identifiers import EventId


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
HASH_A = "a" * 64
HASH_B = "b" * 64


def make_event():
    return AuditEvent(
        event_id=EventId("audit-1"),
        event_type=AuditEventType.SECURITY_DECISION,
        occurred_at=NOW,
        actor=AuditActor("controller-1", "SERVICE"),
        reason="source authentication assessed",
        subject_id="source-1",
        payload_hash=HASH_A,
        evidence=(AuditEvidence("certificate", HASH_B),),
    )


def test_audit_events_are_immutable_and_hash_deterministically():
    event = make_event()
    assert event.event_hash == make_event().event_hash
    with pytest.raises(FrozenInstanceError):
        event.reason = "changed"


def test_correction_is_a_new_linked_event():
    original = make_event()
    correction = original.correction(
        event_id=EventId("audit-2"),
        occurred_at=NOW,
        actor=AuditActor("reviewer-1", "HUMAN"),
        reason="corrected evidence reference",
        payload_hash=HASH_B,
    )
    assert correction.event_id != original.event_id
    assert correction.event_type is AuditEventType.CORRECTION
    assert correction.corrects_event_id == original.event_id
    assert correction.previous_event_hash == original.event_hash
    assert correction.occurred_at == original.occurred_at


def test_correction_may_follow_original_event():
    original = make_event()
    correction = original.correction(
        event_id=EventId("audit-2"),
        occurred_at=NOW + timedelta(seconds=1),
        actor=AuditActor("reviewer-1", "HUMAN"),
        reason="later correction",
        payload_hash=HASH_B,
    )
    assert correction.occurred_at > original.occurred_at


def test_correction_cannot_precede_original_event():
    with pytest.raises(InvariantViolationError):
        make_event().correction(
            event_id=EventId("audit-2"),
            occurred_at=NOW - timedelta(microseconds=1),
            actor=AuditActor("reviewer-1", "HUMAN"),
            reason="retrospective correction",
            payload_hash=HASH_B,
        )


def test_correction_contract_requires_links():
    with pytest.raises(InvariantViolationError):
        AuditEvent(
            event_id=EventId("audit-2"),
            event_type=AuditEventType.CORRECTION,
            occurred_at=NOW,
            actor=AuditActor("reviewer-1", "HUMAN"),
            reason="invalid unlinked correction",
            subject_id="source-1",
            payload_hash=HASH_A,
        )
