from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID

import pytest

from core.domain.errors import InvalidTimestampError, SerializationError
from core.domain.serialization import canonical_json, canonical_sha256, to_canonical_data


class State(str, Enum):
    READY = "READY"


@dataclass(frozen=True)
class Payload:
    amount: Decimal
    operational_date: date
    occurred_at: datetime
    identifier: UUID
    state: State


def test_canonical_json_supports_required_types_and_utc():
    payload = Payload(
        amount=Decimal("10.2500"),
        operational_date=date(2026, 1, 1),
        occurred_at=datetime(2026, 1, 1, 6, tzinfo=timezone(timedelta(hours=-6))),
        identifier=UUID("12345678-1234-5678-1234-567812345678"),
        state=State.READY,
    )
    assert canonical_json(payload) == (
        '{"amount":"10.25","identifier":"12345678-1234-5678-1234-567812345678",'
        '"occurred_at":"2026-01-01T12:00:00.000000Z","operational_date":"2026-01-01",'
        '"state":"READY"}'
    )


def test_mapping_order_does_not_change_json_or_hash():
    left = {"b": 2, "a": Decimal("1.0")}
    right = {"a": Decimal("1.00"), "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_sha256(left) == canonical_sha256(right)
    assert len(canonical_sha256(left)) == 64


def test_naive_datetimes_and_unsupported_values_are_rejected():
    with pytest.raises(InvalidTimestampError):
        to_canonical_data(datetime(2026, 1, 1))
    with pytest.raises(SerializationError):
        canonical_json({"values": {1, 2}})
    with pytest.raises(SerializationError):
        canonical_json({1: "non-string-key"})
