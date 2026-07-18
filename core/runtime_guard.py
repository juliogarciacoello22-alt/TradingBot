# core/runtime_guard.py
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

from core.domain import runtime_policy as _runtime_policy


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
    return _runtime_policy.account_is_safe_non_real(account, SAFE_ACCOUNT_MARKERS)


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
    decision = _runtime_policy.decide_runtime_safety(
        run_mode=run_mode,
        trading_enabled=trading_enabled,
        enable_valid=enable_valid,
        account=account,
        live_trading_approved=live_approved,
        approval_valid=approved_valid,
        allowed_run_modes=ALLOWED_RUN_MODES,
        safe_account_markers=SAFE_ACCOUNT_MARKERS,
    )
    return RuntimeSafety(**decision.__dict__)


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
    decision = _runtime_policy.decide_signal_permission(
        run_mode=run_mode,
        startup_allowed=safety.startup_allowed,
        trading_enabled=enable_trading,
        account=account,
        live_allowed=safety.live_allowed,
        safety_reason=safety.reason,
        allowed_run_modes=ALLOWED_RUN_MODES,
        safe_account_markers=SAFE_ACCOUNT_MARKERS,
    )
    return ExecutionAuthorization(**decision.__dict__)


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
