from __future__ import annotations

import re
from dataclasses import dataclass

from core.domain.errors import InvalidIdentifierError, InvariantViolationError


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, order=True)
class _StringIdentifier:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _IDENTIFIER_PATTERN.fullmatch(self.value):
            raise InvalidIdentifierError(
                f"{type(self).__name__} must match {_IDENTIFIER_PATTERN.pattern}"
            )

    def __str__(self) -> str:
        return self.value


class EventId(_StringIdentifier):
    pass


class IncidentId(_StringIdentifier):
    pass


class RecoveryId(_StringIdentifier):
    pass


class AuthorizationId(_StringIdentifier):
    pass


class SourceId(_StringIdentifier):
    pass


class BootId(_StringIdentifier):
    pass


class LeaseId(_StringIdentifier):
    pass


@dataclass(frozen=True, order=True)
class FencingToken:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int) or self.value <= 0:
            raise InvariantViolationError("fencing token must be a positive integer")

    def is_newer_than(self, other: FencingToken) -> bool:
        return self.value > other.value
