from dataclasses import FrozenInstanceError

import pytest

from core.domain.errors import InvalidIdentifierError, InvariantViolationError
from core.domain.identifiers import (
    AuthorizationId,
    BootId,
    EventId,
    FencingToken,
    IncidentId,
    LeaseId,
    RecoveryId,
    SourceId,
)


@pytest.mark.parametrize(
    "identifier_type",
    [EventId, IncidentId, RecoveryId, AuthorizationId, SourceId, BootId, LeaseId],
)
def test_explicit_identifiers_are_typed_and_deterministic(identifier_type):
    identifier = identifier_type("scope:item-01")
    assert str(identifier) == "scope:item-01"
    assert identifier == identifier_type("scope:item-01")


@pytest.mark.parametrize("value", ["", " white-space", "a/b", "x" * 129])
def test_invalid_identifiers_are_rejected(value):
    with pytest.raises(InvalidIdentifierError):
        EventId(value)


def test_fencing_tokens_are_positive_ordered_value_objects():
    older = FencingToken(1)
    newer = FencingToken(2)
    assert newer.is_newer_than(older)
    assert newer > older
    with pytest.raises(InvariantViolationError):
        FencingToken(0)
    with pytest.raises(InvariantViolationError):
        FencingToken(True)


def test_identifiers_are_frozen():
    identifier = SourceId("source-1")
    with pytest.raises(FrozenInstanceError):
        identifier.value = "source-2"
