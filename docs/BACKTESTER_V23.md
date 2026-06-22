# BiUmolo Backtester v2.3

Estado: implementado en una rama aislada para revision. No esta conectado a
`PipelineLivePRO` y no sustituye ningun componente de produccion.

## Propiedades

- Procesamiento causal, barra por barra y sin acceso al reloj real.
- Niveles BUY-only, SELL-only y neutrales segun la especificacion v2.3.
- VWAP direccional dinamico y reinicio por sesion CME.
- ATR14 de Wilder, VWAP y desviaciones, swings confirmados 2L/2R en 5m/15m.
- Order blocks e imbalances disponibles solo despues de su barra de creacion.
- Maquina de estados con barrida/rechazo, recuperacion, dos cierres de
  confirmacion y caducidad exacta de 10 velas.
- Una posicion abierta, maximo tres senales por dia y cooldown de 20 minutos.
- La senal queda pendiente y la entrada se llena en la apertura de la vela
  siguiente con slippage adverso; entry, riesgo y TP1 se recalculan desde el
  fill real.
- Si la apertura cruza el stop o vuelve invalido el riesgo, la entrada se
  cancela y se registra como rechazo de ejecucion.
- TP1 unico a 1.5R, stop-first cuando stop y TP coinciden en la misma vela.
- Un gap que atraviesa el stop sale desde la apertura adversa mas slippage, no
  desde el stop teorico.
- Todo slippage queda limitado al rango OHLC observado de la vela; si el precio
  deseado cae fuera, se usa el extremo adverso alcanzable.
- El manifiesto registra el commit y timestamp UTC de ejecucion. Estos metadatos
  se inyectan desde la CLI para mantener puro el motor historico.
- Cada rechazo conserva `level_id`, `setup_id` y un `event_id` determinista. Los
  eventos simultaneos de setups distintos permanecen separados y solo se
  deduplican repeticiones exactas del mismo evento.
- El loader audita cada salto temporal: acepta y registra cierres que llegan a
  la apertura CME de las 17:00 CT y huecos cortos de hasta 10 minutos; rechaza
  huecos intradia mayores antes de ejecutar la estrategia.
- `StrategyStreamV23` es la interfaz cerrada compartida por el runner historico
  y futuros consumidores live. Convierte payloads 1m cerrados al mismo `Bar` y
  delega en la misma logica causal; las pruebas exigen paridad de decisiones,
  rechazos y niveles.
- Comision y slippage configurables; resultados diarios, rechazos y curva en R.
- Hash SHA-256 del dataset y de la configuracion en cada manifiesto.

## Ejecucion posterior a la revision

No ejecutar sobre el maestro congelado hasta aprobar el codigo. Despues de la
revision, el comando es:

```powershell
python .\run_backtest_v23.py `
  "RUTA\NQ_1min_2025-11-03_2025-12-31.Last.txt" `
  --output .\backtest_v23_results `
  --commission-round-trip 4.20 `
  --exit-slippage-ticks 1
```

El coste de comision del ejemplo es solo ilustrativo: debe reemplazarse por el
coste real round-trip del instrumento y broker usados.

## Artefactos

- `manifest.json`
- `summary.json`
- `daily.json`
- `equity_curve.json`
- `rejections.json`
- `signals.csv`
- `trades.csv`

La rentabilidad no queda demostrada por compilar o aprobar pruebas unitarias.
Solo puede evaluarse con datos fuera de muestra, costes reales y posterior
forward test en simulacion.
