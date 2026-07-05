# BIUMOLO - Senal Interna vs Trade Real

## Objetivo

Dejar fijada la interpretacion correcta de los contadores shadow/internos frente a trades reales en auditorias de BIUMOLO.

## Estado observado

En la sesion `logs/sessions/20260702_051007`, el log muestra un punto donde:

- `final_state=ENTRY_READY`
- `would_generate_signal=true`
- `real_pipeline_decision=NO_TRADE`
- `setups_entry_ready=16`
- `shadow_trades=16`
- `real_trades=0`

Esto significa que 16 setups llegaron al estado interno/shadow donde la logica shadow marco que habria generado una senal interna, pero el pipeline real no autorizo trade.

## Frase no autorizada

> Hubo 16 trades.

## Criterio de auditoria

En BIUMOLO, ningun contador shadow, recovery interno, `ENTRY_READY`, `would_generate_signal=true` o `shadow_trades` debe reportarse como trade real.

Solo puede hablarse de trade real cuando el pipeline operativo registre decision real de trade y el contador `real_trades` lo confirme.
