# Shadow vs Real Audit Done

## Archivos inspeccionados

- `core/pipeline_live_pro.py`
- `core/microstructure_engine.py`
- `core/ob_engine.py`
- `core/signal_engine_v4_pro.py`
- `core/execution_engine_pro.py`
- `logs/immediate_v2_sell_preentry_diagnostics.jsonl`
- `logs/shadow_trade_outcomes*.jsonl`
- `logs/sessions/*/shadow_trade_outcomes.jsonl`
- `logs/setup_memory_v2_quality*.jsonl`
- `logs/sessions/*/setup_memory_v2_quality.jsonl`

## Archivos creados

- `tools/audit_shadow_vs_real_divergence_simple.py`
- `analysis_reports/shadow_vs_real_flow_map.md`
- `analysis_reports/shadow_vs_real_data_contract.md`
- `analysis_reports/shadow_vs_real_divergence_simple.md`
- `analysis_reports/shadow_vs_real_root_cause.md`
- `analysis_reports/shadow_vs_real_audit_done.md`

## Comandos ejecutados

Ripgrep solicitado:

```powershell
rg -n "IMMEDIATE_V2|entry_ready_v2|quality_check|v2_summary|setup_memory_v2_quality|shadow_trade_outcomes|build_signal_returned_none|build_signal|ob_missing|OBEngine|displacement|momentum|valid_entry_shadow_reason|build_signal_subreason|execution_engine_rejected|vela previa alcista fuerte|duplicate_signal" .
```

Validacion ejecutada con Python bundled porque `python` no esta disponible en PATH en esta shell:

```powershell
& 'C:\Users\julio\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile core\pipeline_live_pro.py
& 'C:\Users\julio\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile tools\audit_shadow_vs_real_divergence_simple.py
& 'C:\Users\julio\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' tools\audit_shadow_vs_real_divergence_simple.py
```

Resultado:

- `py_compile core\pipeline_live_pro.py`: OK.
- `py_compile tools\audit_shadow_vs_real_divergence_simple.py`: OK.
- `tools\audit_shadow_vs_real_divergence_simple.py`: OK, genero `analysis_reports/shadow_vs_real_divergence_simple.md`.
- No se corrio Playback.

## Hallazgos principales

1. SHADOW y REAL no comparten el mismo contrato de datos.
   - SHADOW puede usar displacement/momentum/OB reconstruidos o persistidos.
   - REAL llama `SignalEngineV4.build_signal(...)` con `micro` operativo actual.

2. `quality_pass` / `entry_ready_v2` no equivalen a signal real.
   - En diagnostics actuales: `quality_score=100 + build_signal_returned_none = 4`.

3. `ob_missing` puede existir aunque SHADOW tenga OB.
   - En diagnostics actuales: `ob_strength >= 3 + ob_missing = 1`.

4. `build_signal_returned_none` es demasiado generico.
   - `SignalEngineV4` tiene subreasons internos (`valid_entry_failed`, `delta_filters_failed`, `no_swing_no_scalper`) que no quedan siempre como final reason auditable.

5. V3 no cubre gates reales posteriores.
   - `V3 pass + STOP_FIRST = 2`.
   - `ExecutionEnginePRO` tiene gate de vela previa fuerte que no forma parte de quality/V3.

6. `trade_id` y `setup_id` no son llaves historicas seguras por si solas.
   - Se generan con contadores en memoria y pueden repetirse entre sesiones.
   - El auditor usa side + entry/stop/tp1 redondeados + timestamp cercano + blocker.

## Metricas del auditor simple

- total diagnostics rows: 32
- non_historical diagnostics rows: 6
- joined rows: 32
- count by real_blocker:
  - `build_signal_returned_none`: 4
  - `ob_missing`: 2
- count by result:
  - `TP3_FIRST`: 2
  - `STOP_FIRST`: 2
  - `TP2_FIRST`: 1
  - `TP1_FIRST`: 1
- `quality_score=100 + build_signal_returned_none`: 4
- `ob_strength >= 3 + ob_missing`: 1
- `momentum/displacement aligned + build_signal_returned_none`: 4
- `V3 pass + STOP_FIRST`: 2
- `V3 rejected + TP1_FIRST/TP2_FIRST/TP3_FIRST`: 0

## Causa raiz mas probable

La causa raiz mas probable es una divergencia de contrato entre SHADOW y REAL, combinada con reasons finales demasiado genericos.

SHADOW puede ver un candidato valido porque combina estado persistente, displacement/momentum alternativos y OB shadow. REAL puede terminar en `build_signal_returned_none` u `ob_missing` porque evalua `micro["displacement"]`, `micro["momentum"]` y `micro["ob"]` reales en el punto operativo. Si build_signal si genera signal, todavia puede fallar `ExecutionEnginePRO` por gates no reflejados en quality/V3, como vela previa fuerte.

## Confirmaciones

- No se cambio logica de senales en esta auditoria.
- No se cambio logica de ordenes en esta auditoria.
- No se toco NinjaScript.
- No se implemento V4.
- No se activaron alertas runtime.
- No se activo Telegram.
- No se activo Sim.
- No se activo real trading.

## Siguiente paso recomendado

Fase futura recomendada: no optimizar V3 todavia. Primero agregar una telemetria de diff por candidato que capture en una sola fila:

- contrato SHADOW completo,
- contrato REAL completo,
- `last_build_signal_reason`,
- `last_valid_entry_reason`,
- `real_ob_reason`,
- `shadow_ob_reason`,
- bar/timestamp de SHADOW vs REAL,
- primer gate real que bloquea.

La prueba de esa fase seria una sesion nueva donde cada `build_signal_returned_none` quede clasificado por subreason accionable sin leer consola.

SHADOW_VS_REAL_AUDIT_DONE
NO_V4_IMPLEMENTED
NO_SIGNAL_LOGIC_CHANGED
NO_ORDER_LOGIC_CHANGED
NO_NINJASCRIPT_CHANGED
NO_RUNTIME_ALERTS_ENABLED
NO_SIM_OR_REAL_TRADING_ENABLED
## Nota de control: senal interna vs trade real

Ver `analysis_reports/biumolo_senal_interna_vs_trade_real.md`.

Criterio operativo: `ENTRY_READY`, `would_generate_signal=true`, `shadow_trades` o recuperaciones internas no deben reportarse como trades reales. En la sesion `20260702_051007`, los 16 casos eran setups shadow/internal con `real_pipeline_decision=NO_TRADE` y `real_trades=0`.


## Evidencia granular: 16 ENTRY_READY shadow

Ver `analysis_reports/shadow_entry_ready_16_cases.csv`.

La tabla contiene los 16 setups shadow que llegaron a `ENTRY_READY` con `would_generate_signal=true`. Todos registran `real_pipeline_decision=NO_TRADE`; por tanto, ninguno debe reportarse como trade real.

Distribucion de bloqueadores reales:

- `historical_mode`: 7
- `risk_engine:absorcion en contra`: 4
- `build_signal_returned_none`: 2
- `ob_missing`: 1
- `duplicate_signal`: 1
- `timing_invalid`: 1
