"""Pure deterministic policy decisions for the legacy runtime guard.

This module deliberately accepts already-normalized primitive values.  Reading
configuration, locating accounts, public compatibility models, and observable
side effects remain responsibilities of :mod:`core.runtime_guard`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Collection


@dataclass(frozen=True)
class SafetyPolicyDecision:
    startup_allowed: bool
    run_mode: str
    trading_enabled: bool
    account: str | None
    live_allowed: bool
    live_trading_approved: bool
    reason: str


@dataclass(frozen=True)
class SignalPolicyDecision:
    allowed: bool
    run_mode: str
    account: str | None
    reason: str
    enable_trading: bool


def account_is_safe_non_real(
    account: str | None,
    safe_account_markers: Collection[str],
) -> bool:
    if not account:
        return False
    normalized_account = account.lower()
    return any(marker in normalized_account for marker in safe_account_markers)


def decide_runtime_safety(
    *,
    run_mode: str,
    trading_enabled: bool,
    enable_valid: bool,
    account: str | None,
    live_trading_approved: bool,
    approval_valid: bool,
    allowed_run_modes: Collection[str],
    safe_account_markers: Collection[str],
) -> SafetyPolicyDecision:
    if run_mode not in allowed_run_modes:
        return SafetyPolicyDecision(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=account,
            live_allowed=False,
            live_trading_approved=live_trading_approved,
            reason="invalid_run_mode",
        )

    if not enable_valid:
        return SafetyPolicyDecision(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=False,
            account=account,
            live_allowed=False,
            live_trading_approved=live_trading_approved,
            reason="malformed_enable_trading",
        )

    if not approval_valid:
        return SafetyPolicyDecision(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=account,
            live_allowed=False,
            live_trading_approved=False,
            reason="malformed_live_trading_approved",
        )

    if run_mode in {"PLAYBACK", "PAPER", "PAPER_LIVE"}:
        if trading_enabled and not account_is_safe_non_real(
            account,
            safe_account_markers,
        ):
            return SafetyPolicyDecision(
                startup_allowed=True,
                run_mode=run_mode,
                trading_enabled=trading_enabled,
                account=account,
                live_allowed=False,
                live_trading_approved=live_trading_approved,
                reason="safe_mode_blocks_real_account",
            )

        return SafetyPolicyDecision(
            startup_allowed=True,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=account,
            live_allowed=False,
            live_trading_approved=live_trading_approved,
            reason="safe_mode",
        )

    if not trading_enabled:
        return SafetyPolicyDecision(
            startup_allowed=True,
            run_mode=run_mode,
            trading_enabled=False,
            account=account,
            live_allowed=False,
            live_trading_approved=live_trading_approved,
            reason="live_trading_disabled",
        )

    if not account:
        return SafetyPolicyDecision(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=None,
            live_allowed=False,
            live_trading_approved=live_trading_approved,
            reason="live_account_undetermined",
        )

    if not live_trading_approved:
        return SafetyPolicyDecision(
            startup_allowed=False,
            run_mode=run_mode,
            trading_enabled=trading_enabled,
            account=account,
            live_allowed=False,
            live_trading_approved=False,
            reason="live_trading_not_approved",
        )

    return SafetyPolicyDecision(
        startup_allowed=True,
        run_mode=run_mode,
        trading_enabled=trading_enabled,
        account=account,
        live_allowed=True,
        live_trading_approved=live_trading_approved,
        reason="live_trading_approved",
    )


def decide_signal_permission(
    *,
    run_mode: str,
    startup_allowed: bool,
    trading_enabled: bool,
    account: str | None,
    live_allowed: bool,
    safety_reason: str,
    allowed_run_modes: Collection[str],
    safe_account_markers: Collection[str],
) -> SignalPolicyDecision:
    if run_mode not in allowed_run_modes:
        return SignalPolicyDecision(
            allowed=False,
            run_mode=run_mode,
            account=account,
            reason="invalid_run_mode",
            enable_trading=trading_enabled,
        )

    if not startup_allowed:
        return SignalPolicyDecision(
            allowed=False,
            run_mode=run_mode,
            account=account,
            reason=safety_reason,
            enable_trading=trading_enabled,
        )

    if not trading_enabled:
        return SignalPolicyDecision(
            allowed=False,
            run_mode=run_mode,
            account=account,
            reason="enable_trading_disabled",
            enable_trading=trading_enabled,
        )

    if not account:
        return SignalPolicyDecision(
            allowed=False,
            run_mode=run_mode,
            account=None,
            reason="account_undetermined",
            enable_trading=trading_enabled,
        )

    if run_mode == "LIVE":
        if not live_allowed:
            return SignalPolicyDecision(
                allowed=False,
                run_mode=run_mode,
                account=account,
                reason=safety_reason,
                enable_trading=trading_enabled,
            )
        return SignalPolicyDecision(
            allowed=True,
            run_mode=run_mode,
            account=account,
            reason="allowed_live_approved",
            enable_trading=trading_enabled,
        )

    normalized_account = account.lower()

    if run_mode == "PLAYBACK":
        if "playback" not in normalized_account and "replay" not in normalized_account:
            return SignalPolicyDecision(
                allowed=False,
                run_mode=run_mode,
                account=account,
                reason="playback_requires_playback_account",
                enable_trading=trading_enabled,
            )
    elif run_mode in {"PAPER", "PAPER_LIVE"}:
        if not account_is_safe_non_real(
            normalized_account,
            safe_account_markers,
        ):
            return SignalPolicyDecision(
                allowed=False,
                run_mode=run_mode,
                account=account,
                reason="paper_live_requires_sim_account",
                enable_trading=trading_enabled,
            )

    return SignalPolicyDecision(
        allowed=True,
        run_mode=run_mode,
        account=account,
        reason="allowed",
        enable_trading=trading_enabled,
    )
