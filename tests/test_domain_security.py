from datetime import datetime, timedelta, timezone

import pytest

from core.domain.errors import InvariantViolationError
from core.domain.identifiers import BootId, EventId, FencingToken, LeaseId, SourceId
from core.domain.security import (
    AuthenticationRecord,
    AuthenticationState,
    AuthorityAssertion,
    AuthorityRole,
    BootIdentity,
    Heartbeat,
    Lease,
    LeaseState,
)


UTC_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
HASH = "a" * 64


def test_boot_and_heartbeat_normalize_aware_timestamps_to_utc():
    local = datetime(2026, 1, 1, 6, tzinfo=timezone(timedelta(hours=-6)))
    boot = BootIdentity(BootId("boot-1"), SourceId("source-1"), local)
    heartbeat = Heartbeat(
        EventId("heartbeat-1"),
        SourceId("source-1"),
        BootId("boot-1"),
        FencingToken(1),
        1,
        local,
    )
    assert boot.started_at == UTC_NOW.replace(hour=12)
    assert heartbeat.observed_at == UTC_NOW.replace(hour=12)


def test_verified_authentication_and_authority_require_evidence():
    with pytest.raises(InvariantViolationError):
        AuthenticationRecord(
            SourceId("source-1"),
            BootId("boot-1"),
            AuthenticationState.VERIFIED,
            UTC_NOW,
            "certificate",
        )
    assertion = AuthorityAssertion(
        "Julio",
        AuthorityRole.FINAL_AUTHORITY,
        UTC_NOW,
        (HASH,),
        True,
    )
    assert assertion.verified is True


def test_lease_validity_uses_explicit_observation_time():
    lease = Lease(
        LeaseId("lease-1"),
        SourceId("source-1"),
        BootId("boot-1"),
        FencingToken(2),
        UTC_NOW,
        UTC_NOW + timedelta(minutes=1),
        LeaseState.ACTIVE,
    )
    assert lease.is_valid_at(UTC_NOW + timedelta(seconds=30))
    assert not lease.is_valid_at(UTC_NOW + timedelta(minutes=1))


def test_security_contracts_do_not_duplicate_runtime_guard_models():
    import core.domain.security as security

    assert not hasattr(security, "ExecutionAuthorization")
    assert not hasattr(security, "RuntimeSafety")
