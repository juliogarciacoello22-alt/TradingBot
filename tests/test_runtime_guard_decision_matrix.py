import pytest

from core.runtime_guard import evaluate_signal_permission, validate_runtime_safety


CASES = (
    (
        "D01_default_fail_closed",
        {},
        None,
        (True, "PLAYBACK", False, None, False, False, "safe_mode"),
        (False, "PLAYBACK", None, "enable_trading_disabled", False),
    ),
    (
        "D02_playback_enabled_playback_account",
        {"RUN_MODE": "PLAYBACK", "EnableTrading": "true", "TRADING_ACCOUNT": "playback"},
        {},
        (True, "PLAYBACK", True, "playback", False, False, "safe_mode"),
        (True, "PLAYBACK", "playback", "allowed", True),
    ),
    (
        "D03_playback_enabled_missing_account",
        {"RUN_MODE": "PLAYBACK", "EnableTrading": "true"},
        {},
        (True, "PLAYBACK", True, None, False, False, "safe_mode_blocks_real_account"),
        (False, "PLAYBACK", None, "account_undetermined", True),
    ),
    (
        "D04_playback_rejects_sim_account",
        {"RUN_MODE": "PLAYBACK", "EnableTrading": "true", "TRADING_ACCOUNT": "Sim101"},
        {},
        (True, "PLAYBACK", True, "Sim101", False, False, "safe_mode"),
        (False, "PLAYBACK", "Sim101", "playback_requires_playback_account", True),
    ),
    (
        "D05_paper_allows_sim_account",
        {"RUN_MODE": "PAPER", "EnableTrading": "true", "TRADING_ACCOUNT": "Sim101"},
        {},
        (True, "PAPER", True, "Sim101", False, False, "safe_mode"),
        (True, "PAPER", "Sim101", "allowed", True),
    ),
    (
        "D06_paper_live_allows_paper_marker",
        {"RUN_MODE": "PAPER_LIVE", "EnableTrading": "true", "TRADING_ACCOUNT": "Paper01"},
        {},
        (True, "PAPER_LIVE", True, "Paper01", False, False, "safe_mode"),
        (True, "PAPER_LIVE", "Paper01", "allowed", True),
    ),
    (
        "D07_paper_blocks_real_account",
        {"RUN_MODE": "PAPER", "EnableTrading": "true", "TRADING_ACCOUNT": "REAL-01"},
        {},
        (True, "PAPER", True, "REAL-01", False, False, "safe_mode_blocks_real_account"),
        (False, "PAPER", "REAL-01", "paper_live_requires_sim_account", True),
    ),
    (
        "D08_live_disabled_even_if_approved",
        {
            "RUN_MODE": "LIVE",
            "EnableTrading": "false",
            "TRADING_ACCOUNT": "REAL-01",
            "LIVE_TRADING_APPROVED": "true",
        },
        {},
        (True, "LIVE", False, "REAL-01", False, True, "live_trading_disabled"),
        (False, "LIVE", "REAL-01", "enable_trading_disabled", False),
    ),
    (
        "D09_live_account_undetermined",
        {"RUN_MODE": "LIVE", "EnableTrading": "true", "LIVE_TRADING_APPROVED": "true"},
        {},
        (False, "LIVE", True, None, False, True, "live_account_undetermined"),
        (False, "LIVE", None, "live_account_undetermined", True),
    ),
    (
        "D10_live_not_approved",
        {"RUN_MODE": "LIVE", "EnableTrading": "true", "TRADING_ACCOUNT": "REAL-01"},
        {},
        (False, "LIVE", True, "REAL-01", False, False, "live_trading_not_approved"),
        (False, "LIVE", "REAL-01", "live_trading_not_approved", True),
    ),
    (
        "D11_live_explicitly_approved",
        {
            "RUN_MODE": "LIVE",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "REAL-01",
            "LIVE_TRADING_APPROVED": "true",
        },
        {},
        (True, "LIVE", True, "REAL-01", True, True, "live_trading_approved"),
        (True, "LIVE", "REAL-01", "allowed_live_approved", True),
    ),
    (
        "D12_invalid_mode_precedes_malformed_flags",
        {
            "RUN_MODE": "INVALID",
            "EnableTrading": "maybe",
            "TRADING_ACCOUNT": "REAL-01",
            "LIVE_TRADING_APPROVED": "maybe",
        },
        {},
        (False, "INVALID", False, "REAL-01", False, False, "invalid_run_mode"),
        (False, "INVALID", "REAL-01", "invalid_run_mode", False),
    ),
    (
        "D13_malformed_enable_fails_closed",
        {"RUN_MODE": "PLAYBACK", "EnableTrading": "maybe", "TRADING_ACCOUNT": "playback"},
        {},
        (False, "PLAYBACK", False, "playback", False, False, "malformed_enable_trading"),
        (False, "PLAYBACK", "playback", "malformed_enable_trading", False),
    ),
    (
        "D14_malformed_approval_fails_closed_in_safe_mode",
        {
            "RUN_MODE": "PAPER",
            "EnableTrading": "true",
            "TRADING_ACCOUNT": "Sim101",
            "LIVE_TRADING_APPROVED": "maybe",
        },
        {},
        (False, "PAPER", True, "Sim101", False, False, "malformed_live_trading_approved"),
        (False, "PAPER", "Sim101", "malformed_live_trading_approved", True),
    ),
    (
        "D15_camel_case_enable_has_precedence",
        {
            "RUN_MODE": "PLAYBACK",
            "EnableTrading": "false",
            "ENABLE_TRADING": "true",
            "TRADING_ACCOUNT": "playback",
        },
        {},
        (True, "PLAYBACK", False, "playback", False, False, "safe_mode"),
        (False, "PLAYBACK", "playback", "enable_trading_disabled", False),
    ),
    (
        "D16_signal_account_can_override_env_account",
        {"RUN_MODE": "PAPER", "EnableTrading": "true", "TRADING_ACCOUNT": "REAL-01"},
        {"account": "Sim101"},
        (True, "PAPER", True, "REAL-01", False, False, "safe_mode_blocks_real_account"),
        (True, "PAPER", "Sim101", "allowed", True),
    ),
    (
        "D17_live_safety_account_is_env_only",
        {"RUN_MODE": "LIVE", "EnableTrading": "true", "LIVE_TRADING_APPROVED": "true"},
        {"account": "REAL-01"},
        (False, "LIVE", True, None, False, True, "live_account_undetermined"),
        (False, "LIVE", "REAL-01", "live_account_undetermined", True),
    ),
    (
        "D18_meta_account_precedes_execution_and_env",
        {"RUN_MODE": "PAPER", "EnableTrading": "true", "TRADING_ACCOUNT": "REAL-01"},
        {"meta": {"accountName": "Sim101"}, "execution": {"account": "playback"}},
        (True, "PAPER", True, "REAL-01", False, False, "safe_mode_blocks_real_account"),
        (True, "PAPER", "Sim101", "allowed", True),
    ),
)


@pytest.mark.parametrize(
    ("env", "signal", "expected_safety", "expected_permission"),
    [case[1:] for case in CASES],
    ids=[case[0] for case in CASES],
)
def test_d01_d18_legacy_decision_matrix(
    env,
    signal,
    expected_safety,
    expected_permission,
):
    safety = validate_runtime_safety(env)
    permission = evaluate_signal_permission(signal, env)

    assert tuple(safety.to_dict().values()) == expected_safety
    assert tuple(permission.to_dict().values()) == expected_permission
