# Playback Real-Data SHADOW vs REAL Audit

## 1. Baseline PR17-PR22

- PR17 merged audit-only telemetry and full-path snapshot logging.
- PR18 merged refactor-only changes.
- PR19 merged test-suite sanitation.
- PR20 merged the read-only SHADOW vs REAL auditor:
  `tools/audit_shadow_vs_real_post_pr19.py`.
- PR21 documented the full execution chain and separated server/live,
  auditor/offline, and backtest/playback routes.
- PR22 merged the fixture-based PLAYBACK audit runner:
  `tools/run_playback_audit_session.py`.

This PR23 audit does not change bot behavior. It does not activate V2, does not
change `_valid_entry()`, does not touch risk, execution, dispatch, `send_signal`,
`is_live`, Telegram/WebSocket, runtime mode, `.env`, `.env.example`,
thresholds, scoring, entries, exits, TP/SL, sizing, or filters.

## 2. Sessions Reviewed

The local `logs/sessions` directory was inspected for sessions with populated
audit JSONL artifacts.

| session | feed_events | pipeline_decisions | full_path_snapshots | dispatch_events | telegram_events | classification |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `20260705_150009` | 0 | 0 | 0 | 0 | 0 | empty session artifact |
| `20260705_150822` | 0 | 0 | 0 | 0 | 0 | empty session artifact |
| `20260705_151635` | 0 | 0 | 0 | 0 | 0 | empty session artifact |
| `20260705_153725` | 0 | 0 | 0 | 0 | 0 | empty session artifact |
| `20260705_154619` | 0 | 0 | 0 | 0 | 0 | empty session artifact |
| `20260705_160228` | 0 | 0 | 0 | 0 | 0 | empty session artifact |
| `20260705_161210` | 0 | 0 | 0 | 0 | 0 | empty session artifact |
| `playback_audit_post_pr22` | 2 | 2 | 2 | 1 | 1 | PR22 synthetic fixture |
| `playback_audit_pr22_validation` | 2 | 2 | 2 | 1 | 1 | PR22 synthetic fixture |

The two populated sessions include metadata with:

- `mode`: `PLAYBACK_AUDIT`
- `audit_only`: `true`
- `synthetic_fixture_based`: `true`
- `send_signal_called`: `false`
- `websocket_opened`: `false`
- `telegram_enabled`: `false`
- `real_or_sim_account_required`: `false`
- `orders_sent`: `0`

Therefore, they are useful parser/contract evidence, but they are not
real-data or historical-playback evidence.

## 3. Artifact Availability

Required PR23 evidence target:

- `feed_events.jsonl > 0`
- `pipeline_decisions.jsonl > 0`
- `signal_engine_full_path_snapshots.jsonl > 0`

Result:

- No reviewed timestamped session has the three required files populated.
- The only sessions with all three required files populated are PR22 synthetic
  fixture sessions.
- No versioned historical market dataset was found in the repository for a
  real-data playback run.
- `docs/DATASETS.md` states that raw `.csv.gz`, normalized CSV, and `.Last.txt`
  files stay outside Git, so the absence of versioned real/historical data is
  expected from repository policy.

## 4. SHADOW vs REAL Metrics

The PR20 auditor was executed against the two populated PR22 sessions.

Command:

```powershell
python -B tools/audit_shadow_vs_real_post_pr19.py logs/sessions/playback_audit_post_pr22
python -B tools/audit_shadow_vs_real_post_pr19.py logs/sessions/playback_audit_pr22_validation
```

Both sessions produced the same metrics:

| metric | value |
| --- | ---: |
| `total_snapshots` | 2 |
| `total_build_signal_results` | 2 |
| `total_valid_entry_blocks` | 1 |
| `mitigation_light_true` | 1 |
| `v2_shadow_would_unlock` | 1 |
| `shadow_generated_signals` | 1 |
| `real_generated_signals` | 1 |
| `pipeline_decisions` | 2 |
| `dispatch_events` | 1 |
| `dispatch_allowed` | 0 |
| `dispatch_blocked` | 1 |
| `telegram_events` | 1 |
| `telegram_sent` | 0 |
| `telegram_failed` | 1 |
| `shadow_signal_real_block_cases` | 1 |
| `real_signal_not_dispatched_cases` | 1 |

Reason counts:

| bucket | reason | count |
| --- | --- | ---: |
| build_signal | `valid_entry_failed` | 1 |
| build_signal | `scalper_generated` | 1 |
| valid_entry | `mitigation_light_true` | 1 |
| valid_entry | `entry_filters_passed` | 1 |
| snapshot_blocks | `mitigation_light_true` | 1 |
| dispatch_blocks | `playback_audit_no_dispatch` | 1 |

These metrics validate the PR20/PR22 audit contract, but they must not be
reported as real-data playback results because both source sessions are
synthetic fixtures.

## 5. Interpretation

- SHADOW is not a trade.
- SHADOW/V2 unlock is not authorization to change `_valid_entry()`.
- A generated signal is not an order.
- `dispatch_allowed=0` means there is no evidence of real execution.
- `telegram_sent=0` means there is no evidence of Telegram delivery.
- PR22 fixture rows intentionally include `dispatch_blocked=1` to prove the
  audit path distinguishes generated signals from dispatched orders.
- Empty sessions are not evidence of clean behavior; they only show that no
  usable audit rows exist in those artifacts.

## 6. Evidence Gaps

PR23 did not find a sufficient real/historical playback session.

Missing evidence:

- A populated non-fixture `logs/sessions/<session_id>/feed_events.jsonl`.
- A populated non-fixture `pipeline_decisions.jsonl`.
- A populated non-fixture `signal_engine_full_path_snapshots.jsonl`.
- Case-level real/historical candles or session metadata proving the source is
  real playback data rather than synthetic fixture data.
- A safe process to feed historical/playback bars into an audit-only path while
  preserving no-dispatch guarantees.

Data availability gap:

- Historical NQ/raw playback data is intentionally outside Git per
  `docs/DATASETS.md`.
- No external dataset was imported for this PR.
- The old workspace was not used as implementation source.

## 7. Safe Process Required Next

To produce a true real/historical PR24-style audit, use a controlled external
historical/playback dataset and an audit-only runner that:

- reads historical bars from an explicit local path,
- writes only `logs/sessions/<session_id>/` audit artifacts,
- never imports or starts `server.py`,
- never opens WebSocket,
- never uses Telegram,
- never calls `send_signal`,
- never enables Sim101 or Live,
- records dataset path, row count, time range, timezone, and SHA-256 in
  `session_metadata.json`,
- produces non-empty `feed_events.jsonl`,
  `pipeline_decisions.jsonl`, and
  `signal_engine_full_path_snapshots.jsonl`,
- then runs `tools/audit_shadow_vs_real_post_pr19.py` against that session.

Until that exists, the current evidence supports only parser/contract validation,
not real-data SHADOW vs REAL conclusions.

## 8. Decision

- GO for continued audit-only evidence collection.
- GO for documenting that current populated sessions are synthetic fixtures.
- NO-GO for claiming real/historical playback conclusions from current local
  artifacts.
- NO-GO for V2 functional activation.
- NO-GO for Sim101.
- NO-GO for Live.
- NO-GO for runtime, risk, execution, dispatch, Telegram/WebSocket, or
  `_valid_entry()` changes.
