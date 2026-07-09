# Post-PR27 Signal Quality Audit Plan

## Objective

Audit the post-PR27 PLAYBACK session quality using existing artifacts only.

Primary session:

`logs/sessions/20260709_051536`

## Scope

- `tools/audit_post_pr27_signal_quality.py`
- `tests/test_audit_post_pr27_signal_quality.py`
- generated local report:
  - `analysis_reports/post_pr27_signal_quality_session_20260709_051536.md`

## Safety Contract

The auditor is read-only.

It does not:

- import `server.py`
- run `PipelineLivePRO`
- call `SignalEngineV4`
- call dispatch
- call Telegram
- open WebSockets
- touch `.env`
- activate V2, Sim101, or Live

## Review Targets

- real internal SignalEngine outputs
- shadow unlocks / V2 research counters
- terminal blocker reasons
- missing snapshot fields
- dispatch and Telegram absence

## Interpretation Guard

`real_generated_signals` are internal SignalEngine outputs, not orders.

`shadow_unlocks` are research counters, not V2 activation approval.

`operational_authorization` remains `NO_GO`.
