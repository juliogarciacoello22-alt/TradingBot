from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.domain.common import SESSION_TIME_ZONE
from core.domain.data_integrity import (
    NQNativeMinuteEvent,
    SequenceAssessment,
    SequenceState,
    Timeframe,
    TradingHoursSnapshot,
    TradingSessionSegment,
    VolumeAtPrice,
    assess_sequence,
    timeframe_policy,
)
from core.domain.errors import InvariantViolationError
from core.domain.identifiers import EventId, SourceId


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
HASH_A = "a" * 64
HASH_B = "b" * 64


def trading_hours(**overrides):
    values = {
        "template_id": "ninjatrader-template-id",
        "template_name": "adapter-provided-template",
        "template_version": "2026.1",
        "timezone_name": SESSION_TIME_ZONE,
        "session_id": "session-2026-01-01",
        "operational_date": NOW.date(),
        "segments": (
            TradingSessionSegment(NOW - timedelta(hours=6), NOW + timedelta(hours=6)),
            TradingSessionSegment(NOW + timedelta(hours=6), NOW + timedelta(hours=23)),
        ),
        "early_close": False,
    }
    values.update(overrides)
    return TradingHoursSnapshot(**values)


def make_event(**overrides):
    values = {
        "event_id": EventId("bar-1"),
        "source_id": SourceId("source-1"),
        "sequence": 1,
        "instrument": "NQ",
        "timeframe": "1m",
        "opened_at": NOW,
        "closed_at": NOW + timedelta(minutes=1),
        "is_closed": True,
        "open": Decimal("100.00"),
        "high": Decimal("100.50"),
        "low": Decimal("99.75"),
        "close": Decimal("100.25"),
        "volume": 20,
        "bid_volume": 10,
        "ask_volume": 10,
        "delta": 0,
        "trading_hours": trading_hours(),
        "volume_by_price": (
            VolumeAtPrice(Decimal("100.00"), 4, 6),
            VolumeAtPrice(Decimal("100.25"), 6, 4),
        ),
    }
    values.update(overrides)
    return NQNativeMinuteEvent(**values)


def test_native_event_is_nq_closed_one_minute_and_idempotent():
    event = make_event()
    assert event.instrument == "NQ"
    assert event.timeframe == "1m"
    assert event.trading_hours.timezone_name == "America/Chicago"
    assert event.idempotency_hash == make_event().idempotency_hash


def test_vap_order_is_normalized_and_does_not_change_hash():
    original = make_event()
    inverted = make_event(volume_by_price=tuple(reversed(original.volume_by_price)))
    assert inverted.volume_by_price == original.volume_by_price
    assert inverted.idempotency_hash == original.idempotency_hash


def test_duplicate_vap_prices_are_rejected():
    with pytest.raises(InvariantViolationError):
        make_event(
            volume_by_price=(
                VolumeAtPrice(Decimal("100.00"), 4, 6),
                VolumeAtPrice(Decimal("100.00"), 6, 4),
            )
        )


def test_different_vap_content_changes_hash():
    changed = make_event(
        volume_by_price=(
            VolumeAtPrice(Decimal("100.00"), 5, 5),
            VolumeAtPrice(Decimal("100.25"), 5, 5),
        )
    )
    assert changed.idempotency_hash != make_event().idempotency_hash


def test_trading_hours_snapshot_has_complete_deterministic_identity():
    first = trading_hours()
    reordered = trading_hours(segments=tuple(reversed(first.segments)))
    changed_version = trading_hours(template_version="2026.2")
    assert reordered.segments == first.segments
    assert reordered.snapshot_hash == first.snapshot_hash
    assert changed_version.snapshot_hash != first.snapshot_hash
    assert len(first.snapshot_hash) == 64
    with pytest.raises(FrozenInstanceError):
        first.session_id = "changed"


def test_trading_hours_snapshot_rejects_invalid_identity_and_overlaps():
    with pytest.raises(InvariantViolationError):
        trading_hours(template_id="")
    with pytest.raises(InvariantViolationError):
        trading_hours(timezone_name="UTC")
    with pytest.raises(InvariantViolationError):
        trading_hours(
            segments=(
                TradingSessionSegment(NOW, NOW + timedelta(hours=2)),
                TradingSessionSegment(NOW + timedelta(hours=1), NOW + timedelta(hours=3)),
            )
        )


def test_trading_hours_segments_require_utc_and_positive_duration():
    with pytest.raises(InvariantViolationError):
        TradingSessionSegment(NOW, NOW)
    chicago_offset = timezone(timedelta(hours=-6))
    with pytest.raises(InvariantViolationError):
        TradingSessionSegment(
            NOW.astimezone(chicago_offset),
            (NOW + timedelta(hours=1)).astimezone(chicago_offset),
        )


@pytest.mark.parametrize(
    "override",
    [
        {"instrument": "ES"},
        {"timeframe": "5m"},
        {"is_closed": False},
        {"close": Decimal("100.10")},
        {"delta": 1},
        {"closed_at": NOW + timedelta(minutes=2)},
    ],
)
def test_invalid_native_market_contracts_are_rejected(override):
    with pytest.raises(InvariantViolationError):
        make_event(**override)


def test_timeframe_contracts_authorize_5m_15m_4h_and_disable_30m():
    for timeframe in (Timeframe.FIVE_MINUTES, Timeframe.FIFTEEN_MINUTES, Timeframe.FOUR_HOURS):
        policy = timeframe_policy(timeframe)
        assert policy.derived is True
        assert policy.decision_authorized is True
    thirty = timeframe_policy(Timeframe.THIRTY_MINUTES)
    assert thirty.derived is True
    assert thirty.decision_authorized is False


def test_duplicate_and_conflict_states_are_hash_explicit():
    duplicate = SequenceAssessment(SequenceState.DUPLICATE, 2, 2, HASH_A, HASH_A)
    conflict = SequenceAssessment(SequenceState.CONFLICT, 2, 2, HASH_A, HASH_B)
    assert duplicate.state is SequenceState.DUPLICATE
    assert conflict.state is SequenceState.CONFLICT


def test_sequence_classification_is_deterministic():
    assert assess_sequence(current_sequence=1, previous_sequence=None).state is SequenceState.IN_ORDER
    assert assess_sequence(current_sequence=4, previous_sequence=1).state is SequenceState.GAP
    assert assess_sequence(current_sequence=1, previous_sequence=4).state is SequenceState.REORDERED
    assert assess_sequence(
        current_sequence=4,
        previous_sequence=4,
        existing_hash=HASH_A,
        incoming_hash=HASH_A,
    ).state is SequenceState.DUPLICATE
