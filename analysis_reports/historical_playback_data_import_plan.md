# Historical Playback Data Import Plan

## 1. PR23 Evidence Gap

PR23 reviewed local `logs/sessions` artifacts and found no sufficient
real/historical playback evidence for SHADOW vs REAL conclusions.

Observed state:

- Timestamped sessions existed but had empty JSONL files.
- Populated sessions were PR22 synthetic fixtures.
- The populated PR22 sessions validated parser contracts only.
- No versioned real/historical market dataset was available in the repository.
- `docs/DATASETS.md` says raw `.csv.gz`, normalized CSV, and `.Last.txt` files
  stay outside Git.

PR24 therefore defines and implements a read-only import route for external
historical/playback files without creating fake pipeline decisions or fake
SHADOW metrics.

## 2. Input Formats

Implemented importer:

```powershell
python -B tools/import_historical_playback_readonly.py <source_path>
```

Accepted local file formats:

- CSV with header: `timestamp,open,high,low,close,volume`
- JSON list of bar objects with the same fields
- JSONL with one bar object per line
- NinjaTrader `.Last.txt` / semicolon rows:
  `YYYYMMDD HHMMSS;open;high;low;close;volume`

Pending confirmation:

- canonical provider timezone for each external source,
- instrument/contract metadata,
- official dataset manifest path,
- closure calendar policy for imported feed-only sessions.

## 3. Output Contract

The importer writes only under:

```text
logs/sessions/<session_id>/
```

Generated files:

- `feed_events.jsonl`
- `session_metadata.json`
- `session_summary.json`
- `session_summary.md`
- empty audit-session placeholders:
  - `pipeline_decisions.jsonl`
  - `signal_candidates.jsonl`
  - `signals_enriched.jsonl`
  - `dispatch_events.jsonl`
  - `telegram_events.jsonl`
  - `missed_trade_candidates.jsonl`
  - `signal_engine_full_path_snapshots.jsonl`
  - `server_console.log`

The importer does not write pipeline decisions, snapshots, dispatch events, or
SHADOW/V2 metrics because it does not run the pipeline.

## 4. Minimum Bar Fields

Each imported bar/feed event requires:

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

Validation:

- OHLC values must satisfy `low <= open <= high` and `low <= close <= high`.
- `volume` must be non-negative.
- input must contain at least one bar.

Metadata records:

- `source_type=historical_playback`
- `source_path`
- `source_sha256`
- `input_format`
- `row_count`
- `first_timestamp`
- `last_timestamp`
- `timezone`
- `synthetic_fixture_based`
- `no_dispatch=true`
- `no_live=true`
- `pipeline_processed=false`
- `send_signal_called=false`
- `websocket_opened=false`
- `telegram_enabled=false`
- `orders_sent=0`

`synthetic_fixture_based=false` is valid only when the input file is a real
historical/playback source. Tests use `synthetic_fixture_based=true` where the
source is a test fixture.

## 5. Import vs Pipeline vs SHADOW Audit

Importing data is not the same as processing the pipeline.

Importing data:

- reads a local historical/playback file,
- validates basic bar shape,
- writes feed artifacts,
- records source metadata and SHA-256,
- does not call `build_signal`,
- does not create SHADOW metrics.

Processing by pipeline:

- would build microstructure/context/timing/delta/forecast,
- would call `SignalEngineV4.build_signal(...)`,
- would generate `pipeline_decisions.jsonl` and
  `signal_engine_full_path_snapshots.jsonl` only if a separate safe audit-only
  processor exists.

SHADOW vs REAL auditing:

- consumes populated session artifacts,
- must not infer missing pipeline decisions,
- must not invent build-signal results,
- must not treat imported feed rows as trades.

## 6. Safety

The importer:

- does not change bot behavior,
- does not activate V2,
- does not change `_valid_entry()`,
- does not touch risk, execution, dispatch, `send_signal`, `is_live`,
  Telegram/WebSocket, runtime mode, `.env`, `.env.example`, thresholds, scoring,
  entries, exits, TP/SL, sizing, or filters,
- does not execute orders,
- does not use Sim101,
- does not use Live,
- does not import or start `server.py`,
- does not open WebSockets,
- does not depend on credentials or accounts,
- treats the source file as read-only,
- writes only session artifacts under `logs/sessions/<session_id>/`.

## 7. Evidence Criteria

A session can be called real/historical import evidence if:

- `session_metadata.json` has `source_type=historical_playback`,
- `synthetic_fixture_based=false`,
- `source_sha256` is present,
- `row_count > 0`,
- `feed_events.jsonl` has one row per imported bar,
- metadata identifies source path, time range, timezone, and format.

A session can be called SHADOW vs REAL evidence only if, in addition:

- `pipeline_decisions.jsonl` is populated by a safe audit-only processor,
- `signal_engine_full_path_snapshots.jsonl` is populated by that processor,
- the processor records `no_dispatch=true` and `no_live=true`,
- `dispatch_events.jsonl` shows no real dispatch or is explicitly absent from
  the processing scope.

Feed-only import sessions are not sufficient for SHADOW vs REAL conclusions.

## 8. Next Step After PR24

Use a controlled external historical/playback file and run:

```powershell
python -B tools/import_historical_playback_readonly.py <source_path> --session-id historical_import_<id>
```

Then review:

```powershell
python -B tools/audit_shadow_vs_real_post_pr19.py logs/sessions/historical_import_<id>
```

Expected result after PR24 import only:

- `feed_events.jsonl > 0`
- `pipeline_decisions.jsonl = 0`
- `signal_engine_full_path_snapshots.jsonl = 0`

The next separate PR should add a safe audit-only processor if the goal is to
turn imported bars into REAL/SHADOW pipeline evidence without dispatch.

## 9. Decision

- GO for read-only historical/playback data import.
- GO for feed-level evidence with SHA-256 metadata.
- NO-GO for claiming SHADOW vs REAL metrics from feed-only imports.
- NO-GO for V2 functional activation.
- NO-GO for Sim101.
- NO-GO for Live.
- NO-GO for runtime, risk, execution, dispatch, Telegram/WebSocket, or
  `_valid_entry()` changes.
