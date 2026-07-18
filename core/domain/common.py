from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from core.domain.errors import (
    InvalidTimestampError,
    InvariantViolationError,
)


NQ_INSTRUMENT = "NQ"
NQ_TICK_SIZE = Decimal("0.25")
SESSION_TIME_ZONE = "America/Chicago"
NATIVE_TIMEFRAME = "1m"
AUTHORIZED_DERIVED_TIMEFRAMES = frozenset({"5m", "15m", "4h"})
UNAUTHORIZED_DECISION_TIMEFRAMES = frozenset({"30m"})

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class VerificationState(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


def normalize_utc(value: datetime, *, field_name: str = "timestamp") -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InvalidTimestampError(f"{field_name} must be timezone-aware")
    if value.utcoffset() is None:
        raise InvalidTimestampError(f"{field_name} must have a valid UTC offset")
    return value.astimezone(timezone.utc)


def require_non_empty(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvariantViolationError(f"{field_name} must be a non-empty string")
    return value.strip()


def require_sha256(value: str, *, field_name: str) -> str:
    normalized = require_non_empty(value, field_name=field_name).lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise InvariantViolationError(f"{field_name} must be a lowercase SHA-256 hex digest")
    return normalized
