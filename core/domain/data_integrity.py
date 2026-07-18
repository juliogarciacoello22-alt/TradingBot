from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from core.domain.common import (
    AUTHORIZED_DERIVED_TIMEFRAMES,
    NATIVE_TIMEFRAME,
    NQ_INSTRUMENT,
    NQ_TICK_SIZE,
    SESSION_TIME_ZONE,
    normalize_utc,
    require_non_empty,
    require_sha256,
)
from core.domain.errors import InvariantViolationError
from core.domain.identifiers import EventId, SourceId
from core.domain.serialization import canonical_sha256


class SequenceState(str, Enum):
    IN_ORDER = "IN_ORDER"
    GAP = "GAP"
    REORDERED = "REORDERED"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"


class Timeframe(str, Enum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    FOUR_HOURS = "4h"


@dataclass(frozen=True)
class TimeframePolicy:
    timeframe: Timeframe
    native: bool
    derived: bool
    decision_authorized: bool


TIMEFRAME_POLICIES = MappingProxyType({
    Timeframe.ONE_MINUTE: TimeframePolicy(Timeframe.ONE_MINUTE, True, False, True),
    Timeframe.FIVE_MINUTES: TimeframePolicy(Timeframe.FIVE_MINUTES, False, True, True),
    Timeframe.FIFTEEN_MINUTES: TimeframePolicy(Timeframe.FIFTEEN_MINUTES, False, True, True),
    Timeframe.THIRTY_MINUTES: TimeframePolicy(Timeframe.THIRTY_MINUTES, False, True, False),
    Timeframe.FOUR_HOURS: TimeframePolicy(Timeframe.FOUR_HOURS, False, True, True),
})


@dataclass(frozen=True)
class TradingSessionSegment:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.start_at, datetime) or self.start_at.utcoffset() != timedelta(0):
            raise InvariantViolationError("session segment start_at must be UTC")
        if not isinstance(self.end_at, datetime) or self.end_at.utcoffset() != timedelta(0):
            raise InvariantViolationError("session segment end_at must be UTC")
        start = normalize_utc(self.start_at, field_name="start_at")
        end = normalize_utc(self.end_at, field_name="end_at")
        if end <= start:
            raise InvariantViolationError("session segment end_at must be after start_at")
        object.__setattr__(self, "start_at", start)
        object.__setattr__(self, "end_at", end)


@dataclass(frozen=True)
class TradingHoursSnapshot:
    template_id: str
    template_name: str
    template_version: str
    timezone_name: str
    session_id: str
    operational_date: date
    segments: tuple[TradingSessionSegment, ...]
    early_close: bool
    snapshot_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if self.timezone_name != SESSION_TIME_ZONE:
            raise InvariantViolationError(f"timezone_name must be {SESSION_TIME_ZONE}")
        if not isinstance(self.operational_date, date) or isinstance(self.operational_date, datetime):
            raise InvariantViolationError("operational_date must be a date")
        if not isinstance(self.early_close, bool):
            raise InvariantViolationError("early_close must be boolean")
        template_id = require_non_empty(self.template_id, field_name="template_id")
        template_name = require_non_empty(self.template_name, field_name="template_name")
        template_version = require_non_empty(self.template_version, field_name="template_version")
        session_id = require_non_empty(self.session_id, field_name="session_id")
        if not self.segments:
            raise InvariantViolationError("trading-hours snapshot requires session segments")
        if any(not isinstance(segment, TradingSessionSegment) for segment in self.segments):
            raise InvariantViolationError("segments must contain TradingSessionSegment values")
        segments = tuple(sorted(self.segments, key=lambda segment: segment.start_at))
        if any(current.start_at < previous.end_at for previous, current in zip(segments, segments[1:])):
            raise InvariantViolationError("session segments must not overlap")
        object.__setattr__(self, "template_id", template_id)
        object.__setattr__(self, "template_name", template_name)
        object.__setattr__(self, "template_version", template_version)
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "segments", segments)
        object.__setattr__(
            self,
            "snapshot_hash",
            canonical_sha256(
                {
                    "template_id": template_id,
                    "template_name": template_name,
                    "template_version": template_version,
                    "timezone_name": self.timezone_name,
                    "session_id": session_id,
                    "operational_date": self.operational_date.isoformat(),
                    "segments": segments,
                    "early_close": self.early_close,
                }
            ),
        )


@dataclass(frozen=True)
class VolumeAtPrice:
    price: Decimal
    bid_volume: int
    ask_volume: int

    def __post_init__(self) -> None:
        _require_tick_price(self.price, field_name="price")
        _require_nonnegative_int(self.bid_volume, field_name="bid_volume")
        _require_nonnegative_int(self.ask_volume, field_name="ask_volume")


def _require_nonnegative_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvariantViolationError(f"{field_name} must be a non-negative integer")


def _require_tick_price(value: Decimal, *, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise InvariantViolationError(f"{field_name} must be a finite Decimal")
    if value % NQ_TICK_SIZE != 0:
        raise InvariantViolationError(f"{field_name} must align to NQ tick size {NQ_TICK_SIZE}")


@dataclass(frozen=True)
class NQNativeMinuteEvent:
    event_id: EventId
    source_id: SourceId
    sequence: int
    instrument: str
    timeframe: str
    opened_at: datetime
    closed_at: datetime
    is_closed: bool
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    bid_volume: int
    ask_volume: int
    delta: int
    trading_hours: TradingHoursSnapshot
    volume_by_price: tuple[VolumeAtPrice, ...]

    def __post_init__(self) -> None:
        if self.instrument != NQ_INSTRUMENT:
            raise InvariantViolationError("native market event must be NQ-only")
        if self.timeframe != NATIVE_TIMEFRAME:
            raise InvariantViolationError("native market event must be a closed 1m event")
        if self.is_closed is not True:
            raise InvariantViolationError("native market event must be closed")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise InvariantViolationError("sequence must be a positive integer")
        opened = normalize_utc(self.opened_at, field_name="opened_at")
        closed = normalize_utc(self.closed_at, field_name="closed_at")
        if closed - opened != timedelta(minutes=1):
            raise InvariantViolationError("native event must span exactly one minute")
        object.__setattr__(self, "opened_at", opened)
        object.__setattr__(self, "closed_at", closed)
        for name in ("open", "high", "low", "close"):
            _require_tick_price(getattr(self, name), field_name=name)
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise InvariantViolationError("OHLC bounds are inconsistent")
        if self.high < self.low:
            raise InvariantViolationError("high must not be below low")
        for name in ("volume", "bid_volume", "ask_volume"):
            _require_nonnegative_int(getattr(self, name), field_name=name)
        if self.volume != self.bid_volume + self.ask_volume:
            raise InvariantViolationError("volume must equal bid_volume plus ask_volume")
        if self.delta != self.ask_volume - self.bid_volume:
            raise InvariantViolationError("delta must equal ask_volume minus bid_volume")
        if not self.volume_by_price:
            raise InvariantViolationError("volume_by_price must not be empty")
        normalized_vap = tuple(sorted(self.volume_by_price, key=lambda item: item.price))
        prices = [item.price for item in normalized_vap]
        if len(prices) != len(set(prices)):
            raise InvariantViolationError("volume_by_price prices must be unique")
        if any(price < self.low or price > self.high for price in prices):
            raise InvariantViolationError("volume_by_price must remain inside the bar range")
        if sum(item.bid_volume for item in normalized_vap) != self.bid_volume:
            raise InvariantViolationError("volume_by_price bid total does not match")
        if sum(item.ask_volume for item in normalized_vap) != self.ask_volume:
            raise InvariantViolationError("volume_by_price ask total does not match")
        object.__setattr__(self, "volume_by_price", normalized_vap)

    @property
    def idempotency_hash(self) -> str:
        return canonical_sha256(
            {
                "source_id": str(self.source_id),
                "sequence": self.sequence,
                "instrument": self.instrument,
                "timeframe": self.timeframe,
                "opened_at": self.opened_at,
                "closed_at": self.closed_at,
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "volume": self.volume,
                "bid_volume": self.bid_volume,
                "ask_volume": self.ask_volume,
                "delta": self.delta,
                "trading_hours": self.trading_hours,
                "volume_by_price": self.volume_by_price,
            }
        )


@dataclass(frozen=True)
class SequenceAssessment:
    state: SequenceState
    current_sequence: int
    previous_sequence: int | None
    existing_hash: str | None = None
    incoming_hash: str | None = None

    def __post_init__(self) -> None:
        if self.current_sequence <= 0:
            raise InvariantViolationError("current_sequence must be positive")
        if self.previous_sequence is not None and self.previous_sequence <= 0:
            raise InvariantViolationError("previous_sequence must be positive")
        for field_name in ("existing_hash", "incoming_hash"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, require_sha256(value, field_name=field_name))
        if self.state in {SequenceState.DUPLICATE, SequenceState.CONFLICT}:
            if self.existing_hash is None or self.incoming_hash is None:
                raise InvariantViolationError("duplicate/conflict assessment requires both hashes")
            hashes_match = self.existing_hash == self.incoming_hash
            if self.state is SequenceState.DUPLICATE and not hashes_match:
                raise InvariantViolationError("duplicate hashes must match")
            if self.state is SequenceState.CONFLICT and hashes_match:
                raise InvariantViolationError("conflict hashes must differ")
        if self.state is SequenceState.IN_ORDER and self.previous_sequence is not None:
            if self.current_sequence != self.previous_sequence + 1:
                raise InvariantViolationError("in-order sequence must immediately follow the previous sequence")
        if self.state is SequenceState.GAP:
            if self.previous_sequence is None or self.current_sequence <= self.previous_sequence + 1:
                raise InvariantViolationError("gap sequence must skip at least one sequence number")
        if self.state is SequenceState.REORDERED:
            if self.previous_sequence is None or self.current_sequence >= self.previous_sequence:
                raise InvariantViolationError("reordered sequence must precede the previous sequence")
        if self.state in {SequenceState.DUPLICATE, SequenceState.CONFLICT}:
            if self.previous_sequence is None or self.current_sequence != self.previous_sequence:
                raise InvariantViolationError("duplicate/conflict sequence must match the existing sequence")


def timeframe_policy(timeframe: Timeframe) -> TimeframePolicy:
    return TIMEFRAME_POLICIES[timeframe]


def assess_sequence(
    *,
    current_sequence: int,
    previous_sequence: int | None,
    existing_hash: str | None = None,
    incoming_hash: str | None = None,
) -> SequenceAssessment:
    if previous_sequence is None or current_sequence == previous_sequence + 1:
        state = SequenceState.IN_ORDER
    elif current_sequence > previous_sequence + 1:
        state = SequenceState.GAP
    elif current_sequence < previous_sequence:
        state = SequenceState.REORDERED
    else:
        if existing_hash is None or incoming_hash is None:
            raise InvariantViolationError("same-sequence assessment requires existing and incoming hashes")
        state = (
            SequenceState.DUPLICATE
            if existing_hash.lower() == incoming_hash.lower()
            else SequenceState.CONFLICT
        )
    return SequenceAssessment(
        state=state,
        current_sequence=current_sequence,
        previous_sequence=previous_sequence,
        existing_hash=existing_hash,
        incoming_hash=incoming_hash,
    )


assert {item.value for item in TIMEFRAME_POLICIES if TIMEFRAME_POLICIES[item].derived and TIMEFRAME_POLICIES[item].decision_authorized} == AUTHORIZED_DERIVED_TIMEFRAMES
