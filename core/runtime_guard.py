# core/runtime_guard.py
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional


ALLOWED_RUN_MODES = {"PLAYBACK", "PAPER", "PAPER_LIVE", "LIVE"}
SAFE_ACCOUNT_MARKERS = ("playback", "replay", "sim", "paper")
_DEFAULT_RUN_MODE = "PLAYBACK"
_TRUE_VALUES = {"1", "true", "yes", "on", "y", "t"}
_FALSE_VALUES = {"0", "false", "no", "off", "n", "f"}


@dataclass(frozen=True)
class ExecutionAuthorization:
    allowed: bool
    run_mode: str
    account: Optional[str]
    reason: str
    enable_trading: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeSafety:
    startup_allowed: bool
    run_mode: str
    trading_enabled: bool
    account: Optional[str]
    live_allowed: bool
    live_trading_approved: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_env(environ: Optional[Mapping[str, str]], *keys: str) -> Optional[str]:
    source = environ if environ is not None else os.environ

    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if value:
            return value

    return None


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    normalized = str(value).strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


def _parse_bool_strict(value: Any, default: bool = False) -> tuple[bool, bool]:
    if value is None:
        return default, True

    if isinstance(value, bool):
        return value, True

    normalized = str(value).strip().lower()
    if normalized in _TRUE_VALUES:
        return True, True
    if normalized in _FALSE_VALUES:
        return False, True
    return default, False


def get_run_mode(environ: Optional[Mapping[str, str]] = None) -> str:
    raw_value = _read_env(environ, "RUN_MODE")
    if raw_value is None:
        return _DEFAULT_RUN_MODE
    return raw_value.strip().upper()


def is_live_data_mode(run_mode: str) -> bool:
    return run_mode in {"PAPER", "PAPER_LIVE", "LIVE"}


def get_enable_trading(environ: Optional[Mapping[str, str]] = None) -> bool:
    raw_value = _read_env(environ, "EnableTrading", "ENABLE_TRADING")
    return _parse_bool(raw_value, default=False)


def get_live_trading_approved(environ: Optional[Mapping[str, str]] = None) -> bool:
    raw_value = _read_env(environ, "LIVE_TRADING_APPROVED")
    return _parse_bool(raw_value, default=False)


def _account_is_safe_non_real(account: Optional[str]) -> bool:
    if not account:
        return False
    normalized_account = account.lower()
    return any(marker in normalized_account for marker in SAFE_ACCOUNT_MARKERS)


def _account_is_real(account: Optional[str]) -> bool:
    return bool(account and not _account_is_safe_non_real(account))


def extract_account_name(
    signal: Optional[Mapping[str, Any]],
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    payload = signal or {}

    candidate_keys = (
        "account",
        "accountName",
        "account_name",
        "Account",
        "AccountName",
    )
    for key in candidate_keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        for key in candidate_keys:
            value = meta.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    execution = payload.get("execution")
    if isinstance(execution, Mapping):
        for key in candidate_keys:
            value = execution.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()

    return _read_env(
        environ,
        "TRADING_ACCOUNT",
        "ACCOUNT_NAME",
        "NT_ACCOUNT",
        "NINJATRADER_ACCOUNT",
    )


def validate_runtime_safety(environ: Optional[Mapping[str, str]] = None) -> RuntimeSafety:
    run_mode = get_run_mode(environ)
    account = extract_account_name(None, environ)
    enable_raw = _read_env(environ, "EnableTrading", "ENABLE_TRADING")
    approved_raw = _read_env(environ, "LIVE_TRADING_APPROVED")
    trading_enabled, enable_valid = _parse_bool_strict(enable_raw, default=False)
    live_approved, approved_valid = _parse_bool_strict(approved_raw, default=False)

    if run_mode not in ALLOWED_RUN_MODES:
        return RuntimeSafety(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=account,
            live_allowed=False,
            live_trading_approved=live_approved,
            reason="invalid_run_mode",
        )

    if not enable_valid:
        return RuntimeSafety(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=False,
            account=account,
            live_allowed=False,
            live_trading_approved=live_approved,
            reason="malformed_enable_trading",
        )

    if not approved_valid:
        return RuntimeSafety(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=account,
            live_allowed=False,
            live_trading_approved=False,
            reason="malformed_live_trading_approved",
        )

    if run_mode in {"PLAYBACK", "PAPER", "PAPER_LIVE"}:
        if trading_enabled and not _account_is_safe_non_real(account):
            return RuntimeSafety(
                startup_allowed=True,
                run_mode=run_mode,
                trading_enabled=trading_enabled,
                account=account,
                live_allowed=False,
                live_trading_approved=live_approved,
                reason="safe_mode_blocks_real_account",
            )

        return RuntimeSafety(
            startup_allowed=True,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=account,
            live_allowed=False,
            live_trading_approved=live_approved,
            reason="safe_mode",
        )

    if not trading_enabled:
        return RuntimeSafety(
            startup_allowed=True,
            run_mode=run_mode,
            trading_enabled=False,
            account=account,
            live_allowed=False,
            live_trading_approved=live_approved,
            reason="live_trading_disabled",
        )

    if not account:
        return RuntimeSafety(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=None,
            live_allowed=False,
            live_trading_approved=live_approved,
            reason="live_account_undetermined",
        )

    if not live_approved:
        return RuntimeSafety(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=account,
            live_allowed=False,
            live_trading_approved=False,
            reason="live_trading_not_approved",
        )

    return RuntimeSafety(
        startup_allowed=True,
        run_mode=run_mode,
        trading_enabled=trading_enabled,
        account=account,
        live_allowed=True,
        live_trading_approved=live_approved,
        reason="live_trading_approved",
    )


def log_runtime_safety(safety: RuntimeSafety) -> None:
    print(
        ">>> RUNTIME SAFETY:",
        json.dumps(
            {
                "RUN_MODE": safety.run_mode,
                "trading_enabled": safety.trading_enabled,
                "account": safety.account,
                "live_allowed": safety.live_allowed,
                "reason": safety.reason,
            },
            sort_keys=True,
        ),
    )


def evaluate_signal_permission(
    signal: Optional[Mapping[str, Any]],
    environ: Optional[Mapping[str, str]] = None,
) -> ExecutionAuthorization:
    safety = validate_runtime_safety(environ)
    run_mode = safety.run_mode
    enable_trading = safety.trading_enabled
    account = extract_account_name(signal, environ)

    if run_mode not in ALLOWED_RUN_MODES:
        return ExecutionAuthorization(
            allowed=False,
            run_mode=run_mode,
            account=account,
            reason="invalid_run_mode",
            enable_trading=enable_trading,
        )

    if not safety.startup_allowed:
        return ExecutionAuthorization(
            allowed=False,
            run_mode=run_mode,
            account=account,
            reason=safety.reason,
            enable_trading=enable_trading,
        )

    if not enable_trading:
        return ExecutionAuthorization(
            allowed=False,
            run_mode=run_mode,
            account=account,
            reason="enable_trading_disabled",
            enable_trading=enable_trading,
        )

    if not account:
        return ExecutionAuthorization(
            allowed=False,
            run_mode=run_mode,
            account=None,
            reason="account_undetermined",
            enable_trading=enable_trading,
        )

    if run_mode == "LIVE":
        if not safety.live_allowed:
            return ExecutionAuthorization(
                allowed=False,
                run_mode=run_mode,
                account=account,
                reason=safety.reason,
                enable_trading=enable_trading,
            )
        return ExecutionAuthorization(
            allowed=True,
            run_mode=run_mode,
            account=account,
            reason="allowed_live_approved",
            enable_trading=enable_trading,
        )

    normalized_account = account.lower()

    if run_mode == "PLAYBACK":
        if "playback" not in normalized_account and "replay" not in normalized_account:
            return ExecutionAuthorization(
                allowed=False,
                run_mode=run_mode,
                account=account,
                reason="playback_requires_playback_account",
                enable_trading=enable_trading,
            )
    elif run_mode in {"PAPER", "PAPER_LIVE"}:
        if not _account_is_safe_non_real(normalized_account):
            return ExecutionAuthorization(
                allowed=False,
                run_mode=run_mode,
                account=account,
                reason="paper_live_requires_sim_account",
                enable_trading=enable_trading,
            )

    return ExecutionAuthorization(
        allowed=True,
        run_mode=run_mode,
        account=account,
        reason="allowed",
        enable_trading=enable_trading,
    )


def log_blocked_execution(decision: ExecutionAuthorization) -> None:
    print(
        ">>> ORDER BLOCKED:",
        json.dumps(
            {
                "RUN_MODE": decision.run_mode,
                "account": decision.account,
                "reason": decision.reason,
                "EnableTrading": decision.enable_trading,
            },
            sort_keys=True,
        ),
    )


def sync_api_runtime_mode(api, environ: Optional[Mapping[str, str]] = None) -> str:
    safety = validate_runtime_safety(environ)
    api.run_mode = safety.run_mode
    api.runtime_safety = safety
    api.is_live = bool(safety.live_allowed)
    if hasattr(api, "pipeline"):
        api.pipeline.is_live = bool(safety.live_allowed)
    log_runtime_safety(safety)
    return safety.run_mode
