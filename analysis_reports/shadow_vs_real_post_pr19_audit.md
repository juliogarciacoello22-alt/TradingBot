# SHADOW vs REAL Post-PR19 Audit

## 1. Baseline

- PR17 telemetry/audit merged.
- PR18 refactor-only merged.
- PR19 test-suite sanitation merged.
- Baseline branch before PR20: `main...origin/main`.
- Versioned tests reported OK on the clean checkout before this audit scope:
  `python -B -m unittest discover -s tests -v`.

This PR20 scope starts from the clean post-PR19 baseline. The older working
workspace is not a PR base and should only be treated as external historical
evidence when explicitly cited.

## 2. Scope

- Audit/documentation/reporting only.
- Read-only analysis of already-recorded session artifacts.
- No trading execution.
- No Sim101 or Live activation.
- No changes to operational bot behavior.
- No changes to `_valid_entry()`.
- No replacement of `mitigation_light` with `mitigation_contamination`.
- No changes to risk engine, execution engine, dispatch, `send_signal`,
  `is_live`, Telegram/WebSocket, runtime mode, `.env`, `.env.example`,
  thresholds, scoring, entries, exits, TP/SL, sizing, or filters.

## 3. Contracts

### REAL

REAL means the current operational path in the post-PR19 bot:

- `PipelineLivePRO.process(...)` builds the current microstructure, OB,
  context, timing, delta, and forecast.
- `SignalEngineV4.build_signal(...)` evaluates the operational signal path.
- `_valid_entry(...)` remains the production gate for entry validity.
- Risk, timing, execution validation, deduplication, and `is_live` remain
  downstream gates.
- A generated signal is not the same thing as a dispatched order.

### SHADOW

SHADOW means diagnostics, audit-only counters, and V2/research metadata:

- `last_valid_entry_shadow`.
- V2 unlock indicators such as `valid_entry_ab_shadow_would_unlock` or
  `valid_entry_shadow_without_mitigation_v1`.
- Full-path snapshots written to `signal_engine_full_path_snapshots.jsonl`.
- Any SHADOW signal or V2 unlock is evidence for research only, not
  authorization for Sim101 or Live.

## 4. Metrics To Extract

The reproducible read-only parser is:

```powershell
python -B tools/audit_shadow_vs_real_post_pr19.py logs\sessions\<session_id>
```

Optional markdown output:

```powershell
python -B tools/audit_shadow_vs_real_post_pr19.py logs\sessions\<session_id> --output analysis_reports\shadow_vs_real_post_pr19_metrics.md
```

Required metrics:

- `total_snapshots`
- `total_build_signal_results`
- `total_valid_entry_blocks`
- `mitigation_light_true`
- `v2_shadow_would_unlock`
- `shadow_generated_signals`
- `real_generated_signals`
- `pipeline_decisions`
- `dispatch_events`
- `dispatch_allowed`
- `dispatch_blocked`
- `telegram_events`
- `shadow_signal_real_block_cases`
- `real_signal_not_dispatched_cases`

Reason buckets:

- build-signal reasons
- valid-entry reasons
- snapshot block reasons
- pipeline NO_TRADE reasons, when present
- dispatch block reasons, when present

## 5. Comparison Questions

The audit should answer these without executing trading:

- How many full-path snapshots exist for the session?
- How often did REAL `build_signal` return a generated reason versus a block?
- How often did `_valid_entry()` block, and how often was that
  `mitigation_light_true`?
- How often did SHADOW indicate that V2/research would unlock a case that REAL
  still blocked?
- How often did REAL generate a signal but downstream dispatch/live evidence
  remained blocked or absent?
- Which evidence is missing before any V2 functional proposal can be evaluated?

## 6. Risks

- Do not confuse a SHADOW signal with a real trade.
- Do not confuse a generated signal with a dispatched order.
- Do not treat a V2 unlock as authorization.
- Do not treat `signals_enriched.jsonl` or `signal_candidates.jsonl` as proof of
  broker execution.
- Do not infer Live behavior from historical/no-send sessions.
- Do not use old untracked workspace files as implementation source.

## 7. Evidence Requirements Before Future Work

Before any V2 functional, Sim101, or Live proposal, a later investigation needs:

- A clean session directory produced from the post-PR19 codebase.
- Full-path snapshots for each evaluated candle/candidate.
- Build-signal reason counts.
- Valid-entry reason counts.
- Explicit dispatch/live evidence, or explicit proof that no dispatch/live path
  applied.
- Case-level examples for both:
  - SHADOW suggests signal while REAL blocks.
  - REAL generates signal while dispatch/live blocks or does not apply.
- Human approval for any movement beyond audit.

## 8. Decision

- GO for read-only investigation and evidence collection.
- NO-GO for functional V2 activation.
- NO-GO for Sim101.
- NO-GO for Live.
- NO-GO for treating SHADOW/V2 unlocks as trade authorization.

PR20 is ready only if the diff remains audit/read-only and validation confirms
that no operational engine or runtime behavior changed.
