import json
import os
import sys
from dataclasses import asdict, dataclass
from typing import Mapping, Optional

from core.runtime_guard import (
    evaluate_signal_permission,
    validate_runtime_safety,
)


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Sim101PreflightResult:
    passed: bool
    checks: tuple[PreflightCheck, ...]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
        }


def _read_env(
    environ: Mapping[str, str],
    *keys: str,
) -> Optional[str]:
    for key in keys:
        value = environ.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _parse_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "y", "t"}:
        return True
    if normalized in {"0", "false", "no", "off", "n", "f"}:
        return False
    return None


def run_sim101_preflight(
    environ: Optional[Mapping[str, str]] = None,
) -> Sim101PreflightResult:
    env = dict(os.environ if environ is None else environ)

    run_mode = (_read_env(env, "RUN_MODE") or "").upper()
    enable_trading = _parse_bool(
        _read_env(env, "EnableTrading", "ENABLE_TRADING")
    )
    account = _read_env(
        env,
        "TRADING_ACCOUNT",
        "ACCOUNT_NAME",
        "NT_ACCOUNT",
        "NINJATRADER_ACCOUNT",
    )
    telegram_enabled = _parse_bool(
        _read_env(env, "TELEGRAM_ENABLED")
    )
    live_approved = _parse_bool(
        _read_env(env, "LIVE_TRADING_APPROVED")
    )

    safety = validate_runtime_safety(env)
    authorization = evaluate_signal_permission(
        {"account": account} if account else {},
        env,
    )

    account_normalized = (account or "").lower()
    account_is_sim101 = account_normalized == "sim101"
    account_looks_real = not any(
        marker in account_normalized
        for marker in ("sim", "paper", "playback", "replay")
    )

    checks = (
        PreflightCheck(
            name="run_mode_is_paper",
            passed=run_mode == "PAPER",
            detail=f"RUN_MODE={run_mode or '<missing>'}",
        ),
        PreflightCheck(
            name="trading_explicitly_enabled",
            passed=enable_trading is True,
            detail=f"EnableTrading={enable_trading}",
        ),
        PreflightCheck(
            name="account_is_exact_sim101",
            passed=account_is_sim101,
            detail=f"TRADING_ACCOUNT={account or '<missing>'}",
        ),
        PreflightCheck(
            name="account_is_not_real",
            passed=bool(account) and not account_looks_real,
            detail=f"account={account or '<missing>'}",
        ),
        PreflightCheck(
            name="live_approval_disabled",
            passed=live_approved is False,
            detail=f"LIVE_TRADING_APPROVED={live_approved}",
        ),
        PreflightCheck(
            name="telegram_disabled",
            passed=telegram_enabled is False,
            detail=f"TELEGRAM_ENABLED={telegram_enabled}",
        ),
        PreflightCheck(
            name="runtime_startup_allowed",
            passed=safety.startup_allowed,
            detail=f"reason={safety.reason}",
        ),
        PreflightCheck(
            name="runtime_live_not_allowed",
            passed=not safety.live_allowed,
            detail=f"live_allowed={safety.live_allowed}",
        ),
        PreflightCheck(
            name="signal_permission_allowed",
            passed=authorization.allowed,
            detail=f"reason={authorization.reason}",
        ),
        PreflightCheck(
            name="authorization_is_non_live",
            passed=authorization.run_mode == "PAPER",
            detail=f"run_mode={authorization.run_mode}",
        ),
    )

    return Sim101PreflightResult(
        passed=all(check.passed for check in checks),
        checks=checks,
    )


def main() -> int:
    result = run_sim101_preflight()

    for check in result.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"[{status}] {check.name}: {check.detail}")

    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))

    if result.passed:
        print("SIM101 PREFLIGHT: PASS")
        return 0

    print("SIM101 PREFLIGHT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
