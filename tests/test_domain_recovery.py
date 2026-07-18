import pytest

from core.domain.errors import InvalidStateTransitionError, InvariantViolationError
from core.domain.identifiers import RecoveryId
from core.domain.recovery import (
    LIVE_REVALIDATION_BARS_REQUIRED,
    MAX_RECOVERY_ATTEMPTS,
    BarOrigin,
    RecoveryProcess,
    RecoverySessionBudget,
    RecoveryState,
)


def test_session_allows_at_most_two_independent_recoveries():
    budget = RecoverySessionBudget("session-1").reserve().reserve()
    assert budget.independent_recoveries_started == 2
    with pytest.raises(InvalidStateTransitionError):
        budget.reserve()


def test_recovery_has_three_attempt_budget():
    process = RecoveryProcess(RecoveryId("recovery-1"), "session-1", 1)
    for expected in range(1, MAX_RECOVERY_ATTEMPTS + 1):
        process = process.begin_repair()
        assert process.attempt_count == expected
    exhausted = process.begin_repair()
    assert exhausted.state is RecoveryState.EXHAUSTED


def test_only_twenty_new_live_bars_complete_verification():
    process = RecoveryProcess(RecoveryId("recovery-1"), "session-1", 1)
    process = process.begin_repair().begin_verification()
    for origin in (BarOrigin.REPLAY, BarOrigin.PLAYBACK, BarOrigin.BACKFILL):
        assert process.record_bar(origin) is process
    for _ in range(LIVE_REVALIDATION_BARS_REQUIRED - 1):
        process = process.record_bar(BarOrigin.LIVE)
    assert process.state is RecoveryState.VERIFYING
    assert process.verification_complete is False
    process = process.record_bar(BarOrigin.LIVE)
    assert process.state is RecoveryState.VERIFIED
    assert process.verification_complete is True
    assert process.live_revalidation_bars == 20


def test_verification_cannot_start_before_repair():
    process = RecoveryProcess(RecoveryId("recovery-1"), "session-1", 1)
    with pytest.raises(InvalidStateTransitionError):
        process.begin_verification()


@pytest.mark.parametrize(
    "overrides",
    [
        {"state": RecoveryState.DETECTED, "attempt_count": 1},
        {"state": RecoveryState.DETECTED, "repair_complete": True},
        {"state": RecoveryState.REPAIRING, "attempt_count": 0},
        {"state": RecoveryState.REPAIRING, "attempt_count": 1, "repair_complete": True},
        {"state": RecoveryState.VERIFYING, "attempt_count": 1, "repair_complete": False},
        {
            "state": RecoveryState.VERIFYING,
            "attempt_count": 1,
            "repair_complete": True,
            "live_revalidation_bars": LIVE_REVALIDATION_BARS_REQUIRED,
        },
        {
            "state": RecoveryState.VERIFIED,
            "attempt_count": 1,
            "repair_complete": True,
            "verification_complete": False,
            "live_revalidation_bars": LIVE_REVALIDATION_BARS_REQUIRED,
        },
        {"state": RecoveryState.EXHAUSTED, "attempt_count": 2},
        {"state": RecoveryState.FAILED, "attempt_count": 0},
        {"state": RecoveryState.FAILED, "attempt_count": 1, "live_revalidation_bars": 1},
        {"attempt_count": MAX_RECOVERY_ATTEMPTS + 1},
        {"live_revalidation_bars": LIVE_REVALIDATION_BARS_REQUIRED + 1},
    ],
)
def test_direct_construction_rejects_contradictory_recovery_states(overrides):
    with pytest.raises(InvariantViolationError):
        RecoveryProcess(RecoveryId("recovery-invalid"), "session-1", 1, **overrides)


@pytest.mark.parametrize("count", [-1, 3, True])
def test_session_recovery_counter_rejects_invalid_direct_values(count):
    with pytest.raises(InvariantViolationError):
        RecoverySessionBudget("session-1", independent_recoveries_started=count)


@pytest.mark.parametrize("number", [0, 3, True])
def test_independent_recovery_number_respects_frozen_session_limit(number):
    with pytest.raises(InvariantViolationError):
        RecoveryProcess(RecoveryId("recovery-invalid"), "session-1", number)
