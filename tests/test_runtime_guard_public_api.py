import inspect
import pickle
from dataclasses import FrozenInstanceError, MISSING, fields, is_dataclass

import pytest

import core.runtime_guard as runtime_guard


EXPECTED_SIGNATURES = {
    "get_run_mode": "(environ: Optional[Mapping[str, str]] = None) -> str",
    "is_live_data_mode": "(run_mode: str) -> bool",
    "get_enable_trading": "(environ: Optional[Mapping[str, str]] = None) -> bool",
    "get_live_trading_approved": "(environ: Optional[Mapping[str, str]] = None) -> bool",
    "extract_account_name": (
        "(signal: Optional[Mapping[str, Any]], "
        "environ: Optional[Mapping[str, str]] = None) -> Optional[str]"
    ),
    "validate_runtime_safety": (
        "(environ: Optional[Mapping[str, str]] = None) "
        "-> core.runtime_guard.RuntimeSafety"
    ),
    "log_runtime_safety": "(safety: core.runtime_guard.RuntimeSafety) -> None",
    "evaluate_signal_permission": (
        "(signal: Optional[Mapping[str, Any]], "
        "environ: Optional[Mapping[str, str]] = None) "
        "-> core.runtime_guard.ExecutionAuthorization"
    ),
    "log_blocked_execution": (
        "(decision: core.runtime_guard.ExecutionAuthorization) -> None"
    ),
    "sync_api_runtime_mode": (
        "(api, environ: Optional[Mapping[str, str]] = None) -> str"
    ),
}


def test_public_function_signatures_are_identical_to_baseline():
    actual = {
        name: str(inspect.signature(getattr(runtime_guard, name)))
        for name in EXPECTED_SIGNATURES
    }
    assert actual == EXPECTED_SIGNATURES


def test_public_constants_are_identical_to_baseline():
    assert runtime_guard.ALLOWED_RUN_MODES == {
        "PLAYBACK",
        "PAPER",
        "PAPER_LIVE",
        "LIVE",
    }
    assert runtime_guard.SAFE_ACCOUNT_MARKERS == (
        "playback",
        "replay",
        "sim",
        "paper",
    )


@pytest.mark.parametrize(
    ("model", "field_names"),
    (
        (
            runtime_guard.ExecutionAuthorization,
            ("allowed", "run_mode", "account", "reason", "enable_trading"),
        ),
        (
            runtime_guard.RuntimeSafety,
            (
                "startup_allowed",
                "run_mode",
                "trading_enabled",
                "account",
                "live_allowed",
                "live_trading_approved",
                "reason",
            ),
        ),
    ),
)
def test_public_dataclass_metadata_remains_local_and_frozen(model, field_names):
    assert is_dataclass(model)
    assert model.__module__ == "core.runtime_guard"
    assert tuple(field.name for field in fields(model)) == field_names
    assert all(field.default is MISSING for field in fields(model))

    if model is runtime_guard.ExecutionAuthorization:
        instance = model(False, "PLAYBACK", None, "blocked", False)
        expected_repr = (
            "ExecutionAuthorization(allowed=False, run_mode='PLAYBACK', "
            "account=None, reason='blocked', enable_trading=False)"
        )
    else:
        instance = model(True, "PLAYBACK", False, None, False, False, "safe_mode")
        expected_repr = (
            "RuntimeSafety(startup_allowed=True, run_mode='PLAYBACK', "
            "trading_enabled=False, account=None, live_allowed=False, "
            "live_trading_approved=False, reason='safe_mode')"
        )

    assert repr(instance) == expected_repr
    assert pickle.loads(pickle.dumps(instance)) == instance
    assert instance.to_dict() == {
        field.name: getattr(instance, field.name) for field in fields(model)
    }
    with pytest.raises(FrozenInstanceError):
        instance.reason = "changed"


def test_historical_import_paths_resolve_to_local_models():
    namespace = {}
    exec(
        "from core.runtime_guard import ExecutionAuthorization, RuntimeSafety",
        namespace,
    )
    assert namespace["ExecutionAuthorization"] is runtime_guard.ExecutionAuthorization
    assert namespace["RuntimeSafety"] is runtime_guard.RuntimeSafety
