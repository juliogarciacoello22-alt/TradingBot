# Execution Chain Post-PR20 Audit

## 1. Technical Baseline

- PR17 merged as audit-only telemetry/full-path snapshot work.
- PR18 merged as refactor-only work.
- PR19 merged as test-suite sanitation.
- PR20 merged as SHADOW vs REAL read-only audit.
- Baseline branch for this PR21 audit: post-PR20 `main`, with this report
  prepared on `pr21-execution-chain-audit`.
- Versioned tests OK for this PR21 audit:
  `python -B -m unittest discover -s tests -v` ran 82 tests and passed.

This audit is documentation/reporting only. It does not execute trading, does
not activate V2, and does not change runtime, risk, execution, dispatch,
Telegram/WebSocket, entry logic, thresholds, scoring, exits, TP/SL, sizing, or
filters.

## 2. Entrypoints Found

The versioned entrypoints and execution-chain modules reviewed are:

- `server.py`
  - Creates `API()`.
  - Attaches `api.pipeline = PipelineLivePRO(api)`.
  - Calls `sync_api_runtime_mode(api)` before handling requests/stream data.
  - Exposes `POST /send_signal`.
  - Exposes websocket `/ws`.
  - Exposes websocket `/stream` for NinjaTrader input.
- `auditor_biumolo.py`
  - Offline/probe-style auditor that instantiates engines, builds a synthetic
    candle, calls `SignalEngineV4.build_signal(...)`, and conditionally probes
    risk/execution validation.
  - It is not the server/live route.
- `auditor_biumolo_pro_v2.py`
  - Offline/probe-style auditor with deterministic candles and stubs for
    Telegram/WebSocket.
  - It can call `API.send_signal(...)` against fake transports.
  - It is an auditor path, not proof of live order dispatch.
- `core/pipeline_live_pro.py`
  - Main live/server pipeline class: `PipelineLivePRO`.
  - Processes raw candles/events and owns the REAL chain for server-fed data.
- `core/pipeline_backtest.py`
  - Backtest/playback-style pipeline with injected engines.
  - Maintains internal timeframes and can open in-memory trade records.
  - It is isolated from live feed, live `TimeframeLoader`, live `ExitEngine`,
    live risk, and live dedup according to its module docstring.
- `core/backtester_pro.py`
  - Historical/backtest class with its own internal timeframes and in-memory
    trades.
  - Audit note: it imports `core.signal_engine_v4` and `core.timing_engine`,
    while the current versioned engine file is `core/signal_engine_v4_pro.py`
    and `core/timing_engine_pro.py` exists. In this audit, that is recorded as
    route-state evidence only, not changed.

## 3. REAL Chain

### Server/Live Intake

The server route is:

1. `server.py` loads environment via `load_dotenv()`.
2. `server.py` creates `api = API()`.
3. `server.py` creates `api.pipeline = PipelineLivePRO(api)`.
4. `sync_api_runtime_mode(api)` sets `api.is_live` and `api.pipeline.is_live`
   according to runtime guard state.
5. `/stream` receives NinjaTrader websocket messages.
6. Incoming JSON is parsed.
7. Ping messages are ignored.
8. Manual signal payloads are validated with `execution_engine.validate(...)`
   before `api.send_signal(...)`.
9. Candle payloads are checked with `validate_bar_timestamp(...)`.
10. Accepted candles are pushed through `api.feed.push(msg)`.
11. If accepted, `api.pipeline.process(msg)` runs whether live is allowed or
    not; `is_live` determines downstream send/open behavior.

### PipelineLivePRO Processing

`PipelineLivePRO.process(raw)` is the operational chain for accepted candle
events:

1. Reject ping or malformed payloads.
2. Load timeframes through `self.api.loader.load()`.
3. Enforce warmup/minimum timeframe requirements.
4. Check existing open-trade exits with `ExitEngine`.
5. Compute delta and cumdelta.
6. Build microstructure with `MicrostructureEngine.process(...)`.
7. Attach operational OB with `OBEngine.detect_ob(...)`.
8. Build context with `ContextEngine.build_context(...)`.
9. Build timing with `TimingEngine.build_timing(...)`.
10. Build forecast with `LiquidityForecastEngine.predict(...)`.
11. Call `SignalEngineV4.build_signal(...)`.
12. Emit the full-path audit snapshot to
    `signal_engine_full_path_snapshots.jsonl`.
13. If a signal exists, attach timing metadata.
14. If a signal exists, evaluate `RiskEngine.evaluate(...)`.
15. If risk blocks, the signal is nulled.
16. If timing blocks, the signal is nulled.
17. If a signal remains, validate it with `execution_engine.validate(...)`.
18. If execution validates, it becomes `final_signal`.
19. Dashboard and institutional file logs are updated.
20. If `final_signal` exists, dedup runs.
21. If not duplicate, the signal is logged to `logs/signals.log`.
22. If `self.is_live` is true, `self.api.send_signal(final_signal)` is called
    and `ExitEngine.open_from_signal(...)` is called.
23. If `self.is_live` is false, the signal is not sent.
24. `prev_delta` is updated.
25. A console `PIPELINE DECISION` line is emitted.

### Signal / No Signal Decision

`SignalEngineV4.build_signal(...)` is the signal-engine decision point:

1. Resets `last_build_signal_reason` and `last_valid_entry_reason`.
2. Calls `_valid_entry(micro)`.
3. Blocks with `valid_entry_failed` if `_valid_entry(...)` fails.
4. Blocks with `timing_invalid` if timing says invalid.
5. Loads the last `1m` candle and cumdelta.
6. Applies delta filters.
7. Builds institutional metadata.
8. Tries swing first.
9. Tries scalper second.
10. Returns a signal only if swing or scalper generation succeeds.
11. Otherwise returns `None` with `no_swing_no_scalper`.

`_valid_entry(...)` remains the REAL entry gate. It checks displacement,
momentum, fake displacement, inducement, and `mitigation_light`. PR20/PR21 do
not change this logic.

### Risk, Execution, Dispatch, Live Gates

The observed downstream gates are separate:

- Signal generated by `SignalEngineV4` only means the signal engine returned a
  candidate.
- `RiskEngine.evaluate(...)` can still cancel the candidate.
- Timing can still cancel the candidate.
- `execution_engine.validate(...)` can still reject the candidate.
- Dedup can still discard the candidate.
- `self.is_live` can still prevent sending/opening.
- `API.send_signal(...)` still runs `evaluate_signal_permission(...)`.
- Telegram is opt-in through `TELEGRAM_ENABLED`.
- NinjaTrader delivery requires an attached websocket.

Therefore, a generated signal is not evidence of a dispatched order. Stronger
evidence for downstream delivery requires `dispatch_events.jsonl`,
`telegram_events.jsonl`, websocket send logs, or runtime-guard permission
records. In their absence, the audit must report "not demonstrated" rather
than infer live execution.

## 4. SHADOW Chain

SHADOW is audit/research metadata attached around REAL decisions:

- `SignalEngineV4.last_valid_entry_shadow`.
- `valid_entry_shadow_without_mitigation_v1`.
- `would_pass_valid_entry_without_v1`.
- `valid_entry_shadow_v2_mitigation`.
- `valid_entry_ab_delta`.
- `valid_entry_ab_shadow_would_unlock`.
- `last_valid_entry_reason`.
- `last_build_signal_reason`.
- `signal_engine_full_path_snapshots.jsonl`.

The full-path snapshot includes:

- decision/timestamp identifiers,
- microstructure plus mitigation reason fields,
- timing,
- delta,
- last candle,
- timeframes,
- context,
- forecast,
- price,
- signal-engine stage output,
- missing-field diagnostics.

SHADOW is not trade execution because it does not replace `_valid_entry(...)`,
does not authorize V2, does not bypass risk/execution/dedup/runtime guards, and
does not prove downstream dispatch.

## 5. Separated Routes

### Server / Live Route

Route:

`server.py` -> `API` -> `PipelineLivePRO.process(...)` ->
`SignalEngineV4.build_signal(...)` -> risk/timing/execution/dedup ->
`API.send_signal(...)` only when live gates allow it.

Evidence that demonstrates live/server processing:

- accepted feed events,
- full-path snapshots,
- pipeline decision logs,
- dispatch events,
- Telegram events,
- websocket send evidence,
- runtime-guard permission records.

Evidence that does not by itself demonstrate live execution:

- `build_signal` returned a signal,
- `signals_enriched.jsonl`,
- `signal_candidates.jsonl`,
- SHADOW unlock fields,
- synthetic auditor output.

### Auditor / Offline Route

Route examples:

- `auditor_biumolo.py` instantiates engines and probes a synthetic candle.
- `auditor_biumolo_pro_v2.py` builds deterministic candles and uses fake
  Telegram/WebSocket stubs for `API.send_signal(...)`.

This route is useful for health/probe investigation. It is not equivalent to
live/server flow because it does not receive real `/stream` candles, does not
prove live account permission, and may use synthetic/stubbed transports.

### Backtest / Playback Route

Route examples:

- `core/pipeline_backtest.py` receives candles through `process_candle(...)`,
  maintains internal timeframes, calls `self.signal_engine.build_signal(...)`,
  and records in-memory trades.
- `core/backtester_pro.py` follows a historical candle loop and in-memory trade
  model, but has legacy import references noted above.

Backtest/playback results are research or simulation evidence. They do not
prove live dispatch unless separately connected to runtime/dispatch evidence.

## 6. Evidence Files

Versioned or local evidence reviewed:

- `analysis_reports/pipeline_call_chain.txt`
  - Exists in the clean checkout as untracked local evidence.
  - It is a path/call-site inventory, not behavioral proof.
- `analysis_reports/shadow_vs_real_post_pr19_audit.md`
  - PR20 baseline audit defining REAL vs SHADOW interpretation guards.
- `logs/sessions/*`
  - Existing local session directories:
    `20260705_150009`, `20260705_150822`, `20260705_151635`,
    `20260705_153725`.
  - These must be treated as evidence only if their JSONL files contain rows.
    Empty sessions are not proof of no trades beyond "no recorded evidence in
    this artifact."
- `signal_engine_full_path_snapshots.jsonl`
  - Full-path snapshot evidence.
- `pipeline_decisions.jsonl`
  - Pipeline decision evidence when populated.
- `dispatch_events.jsonl`
  - Dispatch allow/block evidence when populated.
- `telegram_events.jsonl`
  - Telegram send/fail evidence when populated.
- `server_console.log`
  - Console-derived fallback evidence used by summary enrichment.

Required files created by `audit_session_logger.start_session(...)` include:

- `server_console.log`
- `feed_events.jsonl`
- `pipeline_decisions.jsonl`
- `signal_candidates.jsonl`
- `signals_enriched.jsonl`
- `dispatch_events.jsonl`
- `telegram_events.jsonl`
- `missed_trade_candidates.jsonl`
- `signal_engine_full_path_snapshots.jsonl`
- `session_summary.md`
- `session_summary.json`

## 7. Risks

- Confusing a generated signal with an order sent to NinjaTrader or Telegram.
- Confusing SHADOW/V2 unlock with authorization to change `_valid_entry(...)`.
- Treating empty `logs/sessions/*` artifacts as proof of clean trading behavior.
- Treating auditor/offline stub output as live execution evidence.
- Using untracked files from the old workspace as source implementation.
- Treating backtest/playback in-memory trades as live trades.
- Ignoring runtime guard, `is_live`, Telegram opt-in, or websocket connectivity
  when evaluating dispatch.
- Reading `core/backtester_pro.py` as current operational parity without noting
  its legacy import references.

## 8. Decision

- GO for investigation read-only.
- GO for case-level evidence collection from populated session artifacts.
- NO-GO for functional V2 activation.
- NO-GO for Sim101.
- NO-GO for Live.
- NO-GO for touching runtime, risk, execution, dispatch, `_valid_entry()`,
  `send_signal`, `is_live`, Telegram/WebSocket, thresholds, scoring, entries,
  exits, TP/SL, sizing, or filters.

PR21 is ready only if the diff remains documentation/reporting only and
validation confirms no operational engine or runtime behavior changed.
