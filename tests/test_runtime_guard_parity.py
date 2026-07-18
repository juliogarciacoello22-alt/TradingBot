import itertools

from core.runtime_guard import (
    ExecutionAuthorization,
    RuntimeSafety,
    evaluate_signal_permission,
    log_blocked_execution,
    log_runtime_safety,
    sync_api_runtime_mode,
    validate_runtime_safety,
)


_ALLOWED = {"PLAYBACK", "PAPER", "PAPER_LIVE", "LIVE"}
_MARKERS = ("playback", "replay", "sim", "paper")
_TRUE = {"1", "true", "yes", "on", "y", "t"}
_FALSE = {"0", "false", "no", "off", "n", "f"}
_MISSING = object()


def _read(env, *keys):
    for key in keys:
        value = env.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value
    return None


def _strict_bool(value):
    if value is None:
        return False, True
    if isinstance(value, bool):
        return value, True
    normalized = str(value).strip().lower()
    if normalized in _TRUE:
        return True, True
    if normalized in _FALSE:
        return False, True
    return False, False


def _safe(account):
    return bool(account and any(marker in account.lower() for marker in _MARKERS))


def _extract(signal, env):
    payload = signal or {}
    keys = ("account", "accountName", "account_name", "Account", "AccountName")
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    for container_name in ("meta", "execution"):
        container = payload.get(container_name)
        if isinstance(container, dict):
            for key in keys:
                value = container.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
    return _read(
        env,
        "TRADING_ACCOUNT",
        "ACCOUNT_NAME",
        "NT_ACCOUNT",
        "NINJATRADER_ACCOUNT",
    )


def _legacy_safety(env):
    raw_mode = _read(env, "RUN_MODE")
    run_mode = "PLAYBACK" if raw_mode is None else raw_mode.strip().upper()
    account = _extract(None, env)
    trading_enabled, enable_valid = _strict_bool(
        _read(env, "EnableTrading", "ENABLE_TRADING")
    )
    approved, approved_valid = _strict_bool(_read(env, "LIVE_TRADING_APPROVED"))

    def result(startup, live_allowed, reason, *, enabled=trading_enabled, live_approved=approved, selected_account=account):
        return {
            "startup_allowed": startup,
            "run_mode": run_mode,
            "trading_enabled": enabled,
            "account": selected_account,
            "live_allowed": live_allowed,
            "live_trading_approved": live_approved,
            "reason": reason,
        }

    if run_mode not in _ALLOWED:
        return result(False, False, "invalid_run_mode")
    if not enable_valid:
        return result(False, False, "malformed_enable_trading", enabled=False)
    if not approved_valid:
        return result(False, False, "malformed_live_trading_approved", live_approved=False)
    if run_mode in {"PLAYBACK", "PAPER", "PAPER_LIVE"}:
        if trading_enabled and not _safe(account):
            return result(True, False, "safe_mode_blocks_real_account")
        return result(True, False, "safe_mode")
    if not trading_enabled:
        return result(True, False, "live_trading_disabled", enabled=False)
    if not account:
        return result(False, False, "live_account_undetermined", selected_account=None)
    if not approved:
        return result(False, False, "live_trading_not_approved", live_approved=False)
    return result(True, True, "live_trading_approved")


def _legacy_permission(signal, env):
    safety = _legacy_safety(env)
    run_mode = safety["run_mode"]
    enabled = safety["trading_enabled"]
    account = _extract(signal, env)

    def result(allowed, reason, *, selected_account=account):
        return {
            "allowed": allowed,
            "run_mode": run_mode,
            "account": selected_account,
            "reason": reason,
            "enable_trading": enabled,
        }

    if run_mode not in _ALLOWED:
        return result(False, "invalid_run_mode")
    if not safety["startup_allowed"]:
        return result(False, safety["reason"])
    if not enabled:
        return result(False, "enable_trading_disabled")
    if not account:
        return result(False, "account_undetermined", selected_account=None)
    if run_mode == "LIVE":
        if not safety["live_allowed"]:
            return result(False, safety["reason"])
        return result(True, "allowed_live_approved")
    normalized = account.lower()
    if run_mode == "PLAYBACK":
        if "playback" not in normalized and "replay" not in normalized:
            return result(False, "playback_requires_playback_account")
    elif run_mode in {"PAPER", "PAPER_LIVE"} and not _safe(normalized):
        return result(False, "paper_live_requires_sim_account")
    return result(True, "allowed")


def _env(run_mode, enable, approval, account):
    values = {
        "RUN_MODE": run_mode,
        "EnableTrading": enable,
        "LIVE_TRADING_APPROVED": approval,
        "TRADING_ACCOUNT": account,
    }
    return {key: value for key, value in values.items() if value is not _MISSING}


def test_exhaustive_normalized_input_grid_matches_legacy_oracle():
    run_modes = (_MISSING, "", "playback", "PAPER", "PAPER_LIVE", "LIVE", "INVALID")
    booleans = (_MISSING, "", "false", "true", "maybe", True)
    accounts = (_MISSING, "", "playback", "Replay01", "Sim101", "paper-demo", "REAL-01")
    signals = (
        None,
        {},
        {"account": "Sim101"},
        {"meta": {"AccountName": "REAL-02"}},
        {"execution": {"account_name": "playback"}},
    )

    checked = 0
    blocked_to_allowed = 0
    for run_mode, enable, approval, account, signal in itertools.product(
        run_modes,
        booleans,
        booleans,
        accounts,
        signals,
    ):
        env = _env(run_mode, enable, approval, account)
        expected_safety = _legacy_safety(env)
        expected_permission = _legacy_permission(signal, env)
        actual_safety = validate_runtime_safety(env).to_dict()
        actual_permission = evaluate_signal_permission(signal, env).to_dict()

        assert actual_safety == expected_safety
        assert actual_permission == expected_permission
        if not expected_permission["allowed"] and actual_permission["allowed"]:
            blocked_to_allowed += 1
        checked += 1

    assert checked == 8820
    assert blocked_to_allowed == 0


def test_stdout_json_is_byte_for_byte_compatible(capsys):
    safety = RuntimeSafety(True, "PAPER", True, "Sim101", False, False, "safe_mode")
    decision = ExecutionAuthorization(False, "PAPER", "REAL-01", "blocked", True)

    log_runtime_safety(safety)
    log_blocked_execution(decision)

    assert capsys.readouterr().out == (
        '>>> RUNTIME SAFETY: {"RUN_MODE": "PAPER", "account": "Sim101", '
        '"live_allowed": false, "reason": "safe_mode", "trading_enabled": true}\n'
        '>>> ORDER BLOCKED: {"EnableTrading": true, "RUN_MODE": "PAPER", '
        '"account": "REAL-01", "reason": "blocked"}\n'
    )


def test_sync_api_mutations_and_stdout_are_compatible(capsys):
    class Pipeline:
        is_live = True

    class API:
        pipeline = Pipeline()

    api = API()
    run_mode = sync_api_runtime_mode(
        api,
        {
            "RUN_MODE": "LIVE",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "REAL-01",
            "LIVE_TRADING_APPROVED": "true",
        },
    )

    assert run_mode == "LIVE"
    assert api.run_mode == "LIVE"
    assert api.is_live is True
    assert api.pipeline.is_live is True
    assert api.runtime_safety.to_dict() == {
        "startup_allowed": True,
        "run_mode": "LIVE",
        "trading_enabled": True,
        "account": "REAL-01",
        "live_allowed": True,
        "live_trading_approved": True,
        "reason": "live_trading_approved",
    }
    assert capsys.readouterr().out == (
        '>>> RUNTIME SAFETY: {"RUN_MODE": "LIVE", "account": "REAL-01", '
        '"live_allowed": true, "reason": "live_trading_approved", '
        '"trading_enabled": true}\n'
    )
