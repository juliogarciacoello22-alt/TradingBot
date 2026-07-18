from datetime import datetime, timedelta, timezone

import pytest

from core.domain.authorization_documents import (
    AuthorizationCondition,
    AuthorizationDocumentState,
    IncidentAuthorizationDocument,
    IncidentAuthorizationScope,
)
from core.domain.errors import InvalidStateTransitionError, InvariantViolationError
from core.domain.identifiers import AuthorizationId, EventId, IncidentId


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
HASH = "b" * 64


def make_document(**overrides):
    values = {
        "authorization_id": AuthorizationId("auth-1"),
        "incident_id": IncidentId("incident-1"),
        "issued_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
        "issuer": "incident-commander",
        "final_authority": "Julio",
        "scopes": (IncidentAuthorizationScope.REACTIVATION,),
        "conditions": (AuthorizationCondition("verification", "complete"),),
        "resolution": "reactivate the affected source only",
        "document_hash": HASH,
        "evidence_hashes": (HASH,),
    }
    values.update(overrides)
    return IncidentAuthorizationDocument(**values)


def test_document_is_not_assumed_valid_and_failed_verification_is_invalid():
    document = make_document()
    assert document.state is AuthorizationDocumentState.ISSUED
    assert document.signature_verified is False
    invalid = document.verify(
        verified_at=NOW + timedelta(minutes=1),
        signature_verified=False,
        final_authority_verified=True,
        verification_hash=HASH,
    )
    assert invalid.state is AuthorizationDocumentState.INVALID


def test_verified_authorization_is_consumed_once():
    verified = make_document().verify(
        verified_at=NOW + timedelta(minutes=1),
        signature_verified=True,
        final_authority_verified=True,
        verification_hash=HASH,
    )
    consumed = verified.consume(
        consumed_at=NOW + timedelta(minutes=2),
        scope=IncidentAuthorizationScope.REACTIVATION,
        conditions_satisfied=True,
        consumption_event_id=EventId("consume-1"),
    )
    assert consumed.state is AuthorizationDocumentState.CONSUMED
    with pytest.raises(InvalidStateTransitionError):
        consumed.consume(
            consumed_at=NOW + timedelta(minutes=3),
            scope=IncidentAuthorizationScope.REACTIVATION,
            conditions_satisfied=True,
            consumption_event_id=EventId("consume-2"),
        )


def test_expired_authorization_cannot_become_verified():
    expired = make_document().verify(
        verified_at=NOW + timedelta(hours=1),
        signature_verified=True,
        final_authority_verified=True,
        verification_hash=HASH,
    )
    assert expired.state is AuthorizationDocumentState.EXPIRED


def verified_evidence():
    return {
        "signature_verified": True,
        "final_authority_verified": True,
        "verified_at": NOW + timedelta(minutes=1),
        "verification_hash": HASH,
    }


@pytest.mark.parametrize(
    ("consumed_at", "consumption_event_id"),
    [
        (None, None),
        (NOW + timedelta(minutes=2), None),
        (None, EventId("consume-1")),
    ],
)
def test_consumed_state_requires_complete_consumption_evidence(consumed_at, consumption_event_id):
    with pytest.raises(InvariantViolationError):
        make_document(
            state=AuthorizationDocumentState.CONSUMED,
            consumed_at=consumed_at,
            consumption_event_id=consumption_event_id,
            **verified_evidence(),
        )


@pytest.mark.parametrize(
    ("consumed_at", "consumption_event_id"),
    [
        (NOW + timedelta(minutes=2), None),
        (None, EventId("consume-1")),
        (NOW + timedelta(minutes=2), EventId("consume-1")),
    ],
)
def test_non_consumed_state_rejects_any_consumption_evidence(consumed_at, consumption_event_id):
    with pytest.raises(InvariantViolationError):
        make_document(
            consumed_at=consumed_at,
            consumption_event_id=consumption_event_id,
        )


@pytest.mark.parametrize(
    "consumed_at",
    [NOW, NOW + timedelta(hours=1)],
)
def test_consumption_must_follow_verification_and_precede_expiry(consumed_at):
    with pytest.raises(InvariantViolationError):
        make_document(
            state=AuthorizationDocumentState.CONSUMED,
            consumed_at=consumed_at,
            consumption_event_id=EventId("consume-1"),
            **verified_evidence(),
        )
