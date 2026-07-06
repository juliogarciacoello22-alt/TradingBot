# Historical Playback Audit-Only Processor Plan

## 1. Objective

PR25 adds a controlled audit-only processor for sessions produced by PR24.

The processor converts imported historical/playback `feed_events.jsonl` rows
into minimal pipeline evidence without dispatch, Telegram, WebSocket, Sim101,
Live, or order execution.

## 2. Input Contract

Command:

```powershell
python -B tools/process_historical_playback_audit_only.py logs/sessions/<session_id>
```

The target session must already exist and must contain:

- `feed_events.jsonl`
- `session_metadata.json`

Required metadata:

- `source_type=historical_playback`
- `no_dispatch=true`
- `no_live=true`
- `orders_sent=0`

The processor rejects empty feed sessions and sessions that are not marked as
historical playback imports.

## 3. Generated Audit Evidence

The processor writes:

- `pipeline_decisions.jsonl`
- `signal_engine_full_path_snapshots.jsonl`
- `session_metadata.json`
- `session_summary.json`
- `session_summary.md`
- `server_console.log`

It preserves empty:

- `dispatch_events.jsonl`
- `telegram_events.jsonl`

## 4. Interpretation Guard

This is not a SignalEngineV4 replay.

`signal_engine_full_path_snapshots.jsonl` rows are feed-validation snapshots
using the same outer artifact file consumed by the post-PR19 auditor, but they
explicitly record:

- `signal_engine_called=false`
- `build_signal_called=false`
- `signal_is_none=true`
- `dispatch_attempted=false`
- `send_signal_called=false`
- `no_dispatch=true`
- `no_live=true`

Therefore PR25 provides pipeline audit evidence that feed rows were replayed
through a safe audit stage. It does not provide SHADOW vs REAL signal evidence,
generated trade candidates, Sim101 evidence, Live evidence, or order evidence.

## 5. Safety Contract

The processor:

- does not import or start `server.py`,
- does not instantiate `PipelineLivePRO`,
- does not call `SignalEngineV4.build_signal(...)`,
- does not open WebSockets,
- does not call `send_signal`,
- does not use Telegram,
- does not require `.env`,
- does not require credentials,
- does not require Sim101,
- does not require Live,
- does not send orders,
- does not change runtime mode,
- does not activate V2,
- does not change `_valid_entry()`,
- does not touch risk, execution, dispatch, thresholds, scoring, entries,
  exits, TP/SL, sizing, or filters.

## 6. Validation Flow

Focused validation:

```powershell
python -m pytest tests/test_process_historical_playback_audit_only.py
```

Optional combined validation with PR24:

```powershell
python -m pytest tests/test_import_historical_playback_readonly.py tests/test_process_historical_playback_audit_only.py
```

Manual flow:

```powershell
python -B tools/import_historical_playback_readonly.py <source_path> --session-id historical_import_manual
python -B tools/process_historical_playback_audit_only.py logs/sessions/historical_import_manual
python -B tools/audit_shadow_vs_real_post_pr19.py logs/sessions/historical_import_manual
```

Expected after processing:

- `feed_events.jsonl > 0`
- `pipeline_decisions.jsonl > 0`
- `signal_engine_full_path_snapshots.jsonl > 0`
- `dispatch_events.jsonl = 0`
- `telegram_events.jsonl = 0`
- `real_generated_signals = 0`
- `v2_shadow_would_unlock = 0`

## 7. Decision

- GO for audit-only feed replay evidence.
- GO for proving imported feed rows can be converted into non-empty pipeline
  audit artifacts.
- NO-GO for claiming SHADOW vs REAL signal conclusions from PR25 alone.
- NO-GO for V2 functional activation.
- NO-GO for Sim101.
- NO-GO for Live.
- NO-GO for dispatch, Telegram, WebSocket, runtime, risk, execution, or
  `_valid_entry()` changes.

## 8. Next Step After PR25

If deeper evidence is required, the next separate PR must design a safe
engine-level offline processor with explicit dependency contracts before
calling any real signal, microstructure, timing, delta, reaction, risk, or
pipeline code.
