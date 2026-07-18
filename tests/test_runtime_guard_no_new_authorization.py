import inspect

import core.domain.runtime_policy as runtime_policy
import core.runtime_guard as runtime_guard


def test_domain_policy_does_not_define_or_reexport_public_runtime_models():
    assert not hasattr(runtime_policy, "ExecutionAuthorization")
    assert not hasattr(runtime_policy, "RuntimeSafety")
    assert runtime_guard.ExecutionAuthorization.__module__ == "core.runtime_guard"
    assert runtime_guard.RuntimeSafety.__module__ == "core.runtime_guard"


def test_no_phase1a_security_contract_becomes_an_implicit_gate():
    forbidden_parameters = {
        "authority",
        "authentication",
        "lease",
        "lock",
        "security_lock",
        "security_context",
    }
    for function in (
        runtime_policy.decide_runtime_safety,
        runtime_policy.decide_signal_permission,
        runtime_guard.validate_runtime_safety,
        runtime_guard.evaluate_signal_permission,
    ):
        assert forbidden_parameters.isdisjoint(inspect.signature(function).parameters)


def test_legacy_allowed_cases_require_no_new_authorization_objects():
    playback = runtime_guard.evaluate_signal_permission(
        {},
        {
            "RUN_MODE": "PLAYBACK",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "playback",
        },
    )
    live = runtime_guard.evaluate_signal_permission(
        {},
        {
            "RUN_MODE": "LIVE",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "REAL-01",
            "LIVE_TRADING_APPROVED": "true",
        },
    )

    assert playback.allowed is True
    assert playback.reason == "allowed"
    assert live.allowed is True
    assert live.reason == "allowed_live_approved"
