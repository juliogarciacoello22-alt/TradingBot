# core/pipeline_backtest.py

class PipelineBacktestPRO:
    """
    Pipeline Backtest PRO — BIUMOLO INSTITUCIONAL
    ---------------------------------------------
    - Aislado del LIVE
    - Usa Candle PRO + Delta PRO
    - No usa Feed LIVE
    - No usa TimeframeLoader LIVE
    - No usa ExitEngine LIVE
    - No usa RiskEngine LIVE
    - No usa dedup LIVE
    - Reproduce EXACTAMENTE el contrato del pipeline real
    """

    def __init__(self, micro_engine, signal_engine, reaction_engine, tp_engine):
        self.micro_engine   = micro_engine
        self.signal_engine  = signal_engine
        self.reaction_engine = reaction_engine
        self.tp_engine      = tp_engine

        self.prev_delta = None
        self.trades = []

        # timeframes internos del backtest
        self.tf = {
            "1m": [],
            "5m": [],
            "30m": [],
            "4h": []
        }

    # ============================================================
    #   PROCESAR UNA VELA
    # ============================================================
    def process_candle(self, candle):

        # 1. Guardar vela en TF 1m
        self.tf["1m"].append(candle)

        # 2. Delta PRO
        delta = getattr(candle, "delta", None)
        cumdelta = getattr(candle, "cumdelta", None)

        # 3. Microestructura PRO
        micro = self.micro_engine.process(
            candle,
            delta=delta,
            prev_delta=self.prev_delta
        )

        # 4. Contexto institucional (placeholder)
        context = {"trend_4h": None}

        # 5. Timing institucional (placeholder)
        timing = {"valid": True}

        # 6. Forecast institucional (placeholder)
        forecast = None

        # 7. Señal institucional PRO
        signal = self.signal_engine.build_signal(
            tf=self.tf,
            micro=micro,
            context=context,
            timing=timing,
            delta=delta,
            forecast=forecast
        )

        # 8. Abrir trade si hay señal
        if signal:
            self._open_trade(signal, candle, micro, delta, cumdelta)

        # 9. Actualizar prev_delta
        self.prev_delta = delta

    # ============================================================
    #   ABRIR TRADE
    # ============================================================
    def _open_trade(self, signal, candle, micro, delta, cumdelta):

        trade = {
            "side": signal["side"],
            "mode": signal["mode"],
            "entry": signal["entry"],
            "stop": signal["stop"],
            "tp1": signal["tp1"],
            "tp2": signal["tp2"],
            "tp3": signal["tp3"],

            # ============================
            #   DELTA PRO EN ENTRY
            # ============================
            "delta_entry": delta,
            "prev_delta_entry": self.prev_delta,
            "cumdelta_entry": cumdelta,

            # ============================
            #   MICRO PRO EN ENTRY
            # ============================
            "displacement": micro.get("displacement"),
            "momentum": micro.get("momentum"),
            "inducement": micro.get("inducement"),
            "fake_displacement": micro.get("fake_displacement"),
            "absorption": micro.get("absorption"),
            "breaker": micro.get("breaker"),

            # ============================
            #   RAZONES
            # ============================
            "reason": signal.get("reason"),
            "ob": signal.get("ob"),

            # ============================
            #   ESTADO
            # ============================
            "open": True,
            "result": None
        }

        self.trades.append(trade)

    # ============================================================
    #   CERRAR TRADE
    # ============================================================
    def close_trade(self, trade, candle):

        delta = getattr(candle, "delta", None)
        cumdelta = getattr(candle, "cumdelta", None)

        trade["open"] = False
        trade["delta_exit"] = delta
        trade["cumdelta_exit"] = cumdelta

        # resultado institucional
        if trade["side"] == "BUY":
            if candle.low <= trade["stop"]:
                trade["result"] = "SL"
            elif candle.high >= trade["tp3"]:
                trade["result"] = "TP3"
            elif candle.high >= trade["tp2"]:
                trade["result"] = "TP2"
            elif candle.high >= trade["tp1"]:
                trade["result"] = "TP1"
            else:
                trade["result"] = "NONE"

        else:  # SELL
            if candle.high >= trade["stop"]:
                trade["result"] = "SL"
            elif candle.low <= trade["tp3"]:
                trade["result"] = "TP3"
            elif candle.low <= trade["tp2"]:
                trade["result"] = "TP2"
            elif candle.low <= trade["tp1"]:
                trade["result"] = "TP1"
            else:
                trade["result"] = "NONE"

        return trade
