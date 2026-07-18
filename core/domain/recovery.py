from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from core.domain.errors import InvalidStateTransitionError, InvariantViolationError
from core.domain.identifiers import RecoveryId


MAX_RECOVERY_ATTEMPTS = 3
MAX_INDEPENDENT_RECOVERIES_PER_SESSION = 2
LIVE_REVALIDATION_BARS_REQUIRED = 20


class GapState(str, Enum):
    NONE = "NONE"
    DETECTED = "DETECTED"
    REPAIRING = "REPAIRING"
    REPAIRED = "REPAIRED"
    UNRECOVERABLE = "UNRECOVERABLE"


class ReorderState(str, Enum):
    NONE = "NONE"
    DETECTED = "DETECTED"
    BUFFERING = "BUFFERING"
    RESTORED = "RESTORED"
    FAILED = "FAILED"


class BackfillState(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    REQUESTED = "REQUESTED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"


class SynchronizationState(str, Enum):
    UNSYNCHRONIZED = "UNSYNCHRONIZED"
    SYNCHRONIZING = "SYNCHRONIZING"
    SYNCHRONIZED = "SYNCHRONIZED"
    FAILED = "FAILED"


class RecoveryState(str, Enum):
    DETECTED = "DETECTED"
    REPAIRING = "REPAIRING"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    EXHAUSTED = "EXHAUSTED"
    FAILED = "FAILED"


class BarOrigin(str, Enum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    PLAYBACK = "PLAYBACK"
    BACKFILL = "BACKFILL"


def _require_bounded_count(value: int, *, field_name: str, minimum: int, maximum: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise InvariantViolationError(
            f"{field_name} must remain between {minimum} and {maximum}"
        )


@dataclass(frozen=True)
class RecoverySessionBudget:
    session_id: str
    independent_recoveries_started: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise InvariantViolationError("session_id must be non-empty")
        _require_bounded_count(
            self.independent_recoveries_started,
            field_name="independent_recoveries_started",
            minimum=0,
            maximum=MAX_INDEPENDENT_RECOVERIES_PER_SESSION,
        )

    def reserve(self) -> RecoverySessionBudget:
        if self.independent_recoveries_started >= MAX_INDEPENDENT_RECOVERIES_PER_SESSION:
            raise InvalidStateTransitionError("session recovery budget is exhausted")
        return replace(self, independent_recoveries_started=self.independent_recoveries_started + 1)


@dataclass(frozen=True)
class RecoveryProcess:
    recovery_id: RecoveryId
    session_id: str
    independent_recovery_number: int
    state: RecoveryState = RecoveryState.DETECTED
    attempt_count: int = 0
    live_revalidation_bars: int = 0
    repair_complete: bool = False
    verification_complete: bool = False
    gap_state: GapState = GapState.NONE
    reorder_state: ReorderState = ReorderState.NONE
    backfill_state: BackfillState = BackfillState.NOT_REQUESTED
    synchronization_state: SynchronizationState = SynchronizationState.UNSYNCHRONIZED

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id.strip():
            raise InvariantViolationError("session_id must be non-empty")
        _require_bounded_count(
            self.independent_recovery_number,
            field_name="independent_recovery_number",
            minimum=1,
            maximum=MAX_INDEPENDENT_RECOVERIES_PER_SESSION,
        )
        _require_bounded_count(
            self.attempt_count,
            field_name="attempt_count",
            minimum=0,
            maximum=MAX_RECOVERY_ATTEMPTS,
        )
        _require_bounded_count(
            self.live_revalidation_bars,
            field_name="live_revalidation_bars",
            minimum=0,
            maximum=LIVE_REVALIDATION_BARS_REQUIRED,
        )
        if self.verification_complete and not self.repair_complete:
            raise InvariantViolationError("verification cannot complete before repair")
        if self.state is RecoveryState.DETECTED:
            if (
                self.attempt_count != 0
                or self.live_revalidation_bars != 0
                or self.repair_complete
                or self.verification_complete
            ):
                raise InvariantViolationError("detected recovery must be an untouched initial state")
        elif self.state is RecoveryState.REPAIRING:
            if (
                self.attempt_count == 0
                or self.live_revalidation_bars != 0
                or self.repair_complete
                or self.verification_complete
            ):
                raise InvariantViolationError("repairing recovery has contradictory progress")
        elif self.state is RecoveryState.VERIFYING:
            if (
                self.attempt_count == 0
                or not self.repair_complete
                or self.verification_complete
                or self.live_revalidation_bars >= LIVE_REVALIDATION_BARS_REQUIRED
            ):
                raise InvariantViolationError("verifying recovery has contradictory progress")
        elif self.state is RecoveryState.VERIFIED:
            if (
                self.attempt_count == 0
                or not self.repair_complete
                or not self.verification_complete
                or self.live_revalidation_bars != LIVE_REVALIDATION_BARS_REQUIRED
            ):
                raise InvariantViolationError("verified recovery requires repair and twenty new LIVE bars")
        elif self.state is RecoveryState.EXHAUSTED:
            if (
                self.attempt_count != MAX_RECOVERY_ATTEMPTS
                or self.live_revalidation_bars != 0
                or self.repair_complete
                or self.verification_complete
            ):
                raise InvariantViolationError("exhausted recovery must consume exactly the repair-attempt budget")
        elif self.state is RecoveryState.FAILED:
            if self.attempt_count == 0 or self.verification_complete:
                raise InvariantViolationError("failed recovery must follow an attempt and cannot be verified")
            if not self.repair_complete and self.live_revalidation_bars != 0:
                raise InvariantViolationError("failed unrepaired recovery cannot contain revalidation bars")
            if self.live_revalidation_bars == LIVE_REVALIDATION_BARS_REQUIRED:
                raise InvariantViolationError("failed recovery cannot contain a complete LIVE revalidation window")

    def begin_repair(self) -> RecoveryProcess:
        if self.state not in {RecoveryState.DETECTED, RecoveryState.REPAIRING}:
            raise InvalidStateTransitionError("repair cannot begin from the current state")
        if self.attempt_count >= MAX_RECOVERY_ATTEMPTS:
            return replace(self, state=RecoveryState.EXHAUSTED)
        return replace(
            self,
            state=RecoveryState.REPAIRING,
            attempt_count=self.attempt_count + 1,
        )

    def begin_verification(self) -> RecoveryProcess:
        if self.state is not RecoveryState.REPAIRING:
            raise InvalidStateTransitionError("verification requires an active repair")
        return replace(
            self,
            state=RecoveryState.VERIFYING,
            repair_complete=True,
            live_revalidation_bars=0,
        )

    def record_bar(self, origin: BarOrigin) -> RecoveryProcess:
        if self.state is not RecoveryState.VERIFYING:
            raise InvalidStateTransitionError("bars count only during recovery verification")
        if origin is not BarOrigin.LIVE:
            return self
        count = self.live_revalidation_bars + 1
        if count == LIVE_REVALIDATION_BARS_REQUIRED:
            return replace(
                self,
                live_revalidation_bars=count,
                verification_complete=True,
                state=RecoveryState.VERIFIED,
            )
        return replace(self, live_revalidation_bars=count)
