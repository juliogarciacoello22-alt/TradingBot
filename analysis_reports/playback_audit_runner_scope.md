# PLAYBACK Audit Runner Scope

## Purpose

PR22 adds a safe, reproducible PLAYBACK audit runner that generates populated
session artifacts for SHADOW vs REAL analysis.

The runner is fixture-based and audit-only. It is not a trading simulator, not
a Sim101 runner, and not evidence of live execution.

## Baseline

- PR17: audit-only telemetry/full-path snapshots.
- PR18: refactor-only.
- PR19: test-suite sanitation.
- PR20: SHADOW vs REAL read-only auditor.
- PR21: execution-chain documentation.

## Runner

Command:

```powershell
python -B tools/run_playback_audit_session.py
```

Deterministic session id:

```powershell
python -B tools/run_playback_audit_session.py --session-id playback_audit_manual
```

The runner writes `logs/sessions/<session_id>/` and prints the session path.

## Generated Artifacts

The runner creates the audit-session file set used by `audit_session_logger` and
PR20 tooling, including:

- `feed_events.jsonl`
- `pipeline_decisions.jsonl`
- `signal_engine_full_path_snapshots.jsonl`
- `signal_candidates.jsonl`
- `signals_enriched.jsonl`
- `dispatch_events.jsonl`
- `telegram_events.jsonl`
- `missed_trade_candidates.jsonl`
- `session_metadata.json`
- `session_summary.json`
- `session_summary.md`
- `server_console.log`

The minimum required artifacts are non-empty:

- `feed_events.jsonl`
- `pipeline_decisions.jsonl`
- `signal_engine_full_path_snapshots.jsonl`

## Safety Contract

The runner:

- does not import or start `server.py`,
- does not import or instantiate `PipelineLivePRO`,
- does not open WebSockets,
- does not call `send_signal`,
- does not use Telegram,
- does not require `.env`,
- does not require a real account,
- does not require Sim101,
- does not send orders,
- does not change runtime mode,
- does not activate V2,
- does not change `_valid_entry()`,
- does not touch risk, execution, dispatch, thresholds, scoring, entries,
  exits, TP/SL, sizing, or filters.

`dispatch_events.jsonl` and `telegram_events.jsonl` are populated with explicit
blocked/not-sent audit rows so downstream reports can distinguish generated
signals from dispatched orders.

## Validation Flow

1. Run the unit suite:

```powershell
python -B -m unittest discover -s tests -v
```

2. Generate a fixture audit session:

```powershell
python -B tools/run_playback_audit_session.py --session-id playback_audit_manual
```

3. Run the PR20 SHADOW vs REAL auditor:

```powershell
python -B tools/audit_shadow_vs_real_post_pr19.py logs/sessions/playback_audit_manual
```

## Decision

- GO for audit-only artifact generation.
- GO for SHADOW vs REAL parser validation against populated JSONL files.
- NO-GO for V2 functional activation.
- NO-GO for Sim101.
- NO-GO for Live.
- NO-GO for dispatch, Telegram, WebSocket, runtime, risk, or execution changes.
