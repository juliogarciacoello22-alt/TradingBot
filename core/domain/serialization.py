from __future__ import annotations

import hashlib
import json
import math
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping
from uuid import UUID

from core.domain.common import normalize_utc
from core.domain.errors import SerializationError


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise SerializationError("non-finite Decimal values are not canonical")
    if value == 0:
        return "0"
    normalized = value.normalize()
    return format(normalized, "f")


def _canonical_datetime(value: datetime) -> str:
    utc_value = normalize_utc(value)
    return utc_value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def to_canonical_data(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SerializationError("non-finite float values are not canonical")
        return value
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value).lower()
    if isinstance(value, Enum):
        return to_canonical_data(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_canonical_data(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SerializationError("canonical JSON object keys must be strings")
            output[key] = to_canonical_data(item)
        return output
    if isinstance(value, (list, tuple)):
        return [to_canonical_data(item) for item in value]
    raise SerializationError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        to_canonical_data(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
