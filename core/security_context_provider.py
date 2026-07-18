"""Application-level protocol for obtaining atomic security snapshots.

This module intentionally contains no provider implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from core.domain.common import require_non_empty, require_sha256
from core.domain.errors import InvariantViolationError
from core.domain.identifiers import BootId, FencingToken, SourceId
from core.domain.security_context import SecurityContextSnapshot


class SecurityContextProviderContractError(RuntimeError):
    """A provider implementation violated the application protocol."""


class ProviderFailureCode(str, Enum):
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    PARTIAL_SNAPSHOT = "PARTIAL_SNAPSHOT"
    INVALID_SNAPSHOT = "INVALID_SNAPSHOT"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    HASH_MISMATCH = "HASH_MISMATCH"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class SecurityContextRequest:
    request_id: str
    expected_source_id: SourceId | None
    expected_boot_id: BootId | None
    minimum_generation: int | None
    minimum_fencing_token: FencingToken | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            require_non_empty(self.request_id, field_name="request_id"),
        )
        if self.minimum_generation is not None and (
            isinstance(self.minimum_generation, bool)
            or not isinstance(self.minimum_generation, int)
            or self.minimum_generation < 0
        ):
            raise InvariantViolationError("minimum_generation must be non-negative")
        if self.expected_source_id is not None and not isinstance(
            self.expected_source_id, SourceId
        ):
            raise InvariantViolationError("expected_source_id is invalid")
        if self.expected_boot_id is not None and not isinstance(
            self.expected_boot_id, BootId
        ):
            raise InvariantViolationError("expected_boot_id is invalid")
        if self.minimum_fencing_token is not None and not isinstance(
            self.minimum_fencing_token, FencingToken
        ):
            raise InvariantViolationError("minimum_fencing_token is invalid")


@dataclass(frozen=True)
class ProviderFailure:
    code: ProviderFailureCode
    safe_detail_code: str
    retryable: bool
    evidence_hashes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, ProviderFailureCode):
            raise InvariantViolationError("provider failure code is invalid")
        object.__setattr__(
            self,
            "safe_detail_code",
            require_non_empty(self.safe_detail_code, field_name="safe_detail_code"),
        )
        if not isinstance(self.retryable, bool):
            raise InvariantViolationError("retryable must be bool")
        hashes = tuple(
            sorted(
                {
                    require_sha256(item, field_name="evidence_hash")
                    for item in self.evidence_hashes
                }
            )
        )
        object.__setattr__(self, "evidence_hashes", hashes)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "safe_detail_code": self.safe_detail_code,
            "retryable": self.retryable,
            "evidence_hashes": self.evidence_hashes,
        }


@dataclass(frozen=True)
class SecurityContextProviderResult:
    snapshot: SecurityContextSnapshot | None
    failure: ProviderFailure | None

    def __post_init__(self) -> None:
        if (self.snapshot is None) == (self.failure is None):
            raise SecurityContextProviderContractError(
                "exactly one of snapshot or failure must be supplied"
            )
        if self.snapshot is not None and not isinstance(
            self.snapshot, SecurityContextSnapshot
        ):
            raise SecurityContextProviderContractError("snapshot has an invalid type")
        if self.failure is not None and not isinstance(self.failure, ProviderFailure):
            raise SecurityContextProviderContractError("failure has an invalid type")

    @classmethod
    def success(cls, snapshot: SecurityContextSnapshot) -> SecurityContextProviderResult:
        if not isinstance(snapshot, SecurityContextSnapshot):
            raise SecurityContextProviderContractError("snapshot has an invalid type")
        return cls(snapshot=snapshot, failure=None)

    @classmethod
    def failed(cls, failure: ProviderFailure) -> SecurityContextProviderResult:
        if not isinstance(failure, ProviderFailure):
            raise SecurityContextProviderContractError("failure has an invalid type")
        return cls(snapshot=None, failure=failure)


@runtime_checkable
class SecurityContextProvider(Protocol):
    async def get_snapshot(
        self,
        request: SecurityContextRequest,
        *,
        timeout_seconds: float,
    ) -> SecurityContextProviderResult:
        """Return one atomic snapshot generation or one typed failure."""

    async def aclose(self) -> None:
        """Release provider-owned resources without producing evidence."""
