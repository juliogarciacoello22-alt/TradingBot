# core/execution_engine_pro.py

print(">>> BIUMOLO — EXECUTION ENGINE PRO ACTIVADO <<<")


class ExecutionEnginePRO:
    """
    Execution Engine PRO — Institucional
    ------------------------------------
    Valida la señal FINAL generada por SignalEngine V4 PRO.
    Compatible con:
    - Microestructura PRO
    - Delta PRO
    - OB PRO
    - Forecast PRO
    - Context PRO
    - Timing PRO
    - TPEngine PRO
    """

    def __init__(self):
        pass

    # ============================================================
    #   FUERZA DEL CUERPO DE LA VELA
    # ============================================================
    def _body_strength(self, candle):
        rango = candle.high - candle.low
        if rango <= 0:
            return 0
        return abs(candle.close - candle.open) / rango

    # ============================================================
    #   ORDEN INSTITUCIONAL DE TPs
    # ============================================================
    def _validate_tp_order(self, side, entry, tps):
        """
        BUY  → entry < TP1 < TP2 < TP3
        SELL → entry > TP1 > TP2 > TP3
        """
        tps = [tp for tp in tps if tp is not None]

        if not tps:
            return False, "sin TPs válidos"

        if len(tps) != len(set(tps)):
            return False, "TPs duplicados"

        if side == "BUY":
            for i in range(len(tps) - 1):
                if not (entry < tps[i] < tps[i + 1]):
                    return False, "orden de TPs inválido (BUY)"

        if side == "SELL":
            for i in range(len(tps) - 1):
                if not (entry > tps[i] > tps[i + 1]):
                    return False, "orden de TPs inválido (SELL)"

        return True, "ok"

    # ============================================================
    #   VALIDACIÓN PRINCIPAL
    # ============================================================
    def validate(self, tf, micro, signal, context=None, timing=None, delta=None):
        """
        tf:        timeframes completos
        micro:     microestructura PRO
        signal:    señal generada por SignalEngine V4 PRO
        context:   contexto institucional
        timing:    timing institucional
        delta:     {delta, cumdelta}
        """

        # ------------------------------------------------------------
        # 0. Señal vacía
        # ------------------------------------------------------------
        if not signal:
            return False, "no signal"

        side  = signal.get("side")
        entry = signal.get("entry")
        stop  = signal.get("stop")
        tp1   = signal.get("tp1")
        tp2   = signal.get("tp2")
        tp3   = signal.get("tp3")
        score = signal.get("score", 0)
        meta  = signal.get("meta", {})
        mode  = signal.get("mode")  # SCALPER / SWING

        # ------------------------------------------------------------
        # 1. Dirección válida
        # ------------------------------------------------------------
        if side not in ("BUY", "SELL"):
            return False, "side inválido"

        # ------------------------------------------------------------
        # 2. Microestructura PRO
        # ------------------------------------------------------------
        if micro.get("fake_displacement"):
            return False, "fake displacement"

        if micro.get("mitigation_light"):
            return False, "mitigación previa"

        absorption = micro.get("absorption")
        if side == "BUY" and absorption == "sell":
            return False, "absorción en contra"
        if side == "SELL" and absorption == "buy":
            return False, "absorción en contra"

        # ------------------------------------------------------------
        # 3. Entry / Stop válidos
        # ------------------------------------------------------------
        if entry is None or stop is None:
            return False, "sin niveles (entry/stop)"

        dist = abs(entry - stop)
        if dist < 0.25:
            return False, "stop demasiado cerca"

        # ------------------------------------------------------------
        # 4. RR mínimo institucional
        # ------------------------------------------------------------
        if tp1 is not None:
            rr = abs(tp1 - entry) / dist
            if rr < 1.2:
                return False, f"RR insuficiente ({rr:.2f})"

        # ------------------------------------------------------------
        # 5. Vela previa fuerte en contra
        # ------------------------------------------------------------
        candle_prev = tf["1m"][-2] if tf.get("1m") and len(tf["1m"]) >= 2 else None

        if candle_prev:
            prev_strength = self._body_strength(candle_prev)

            if side == "BUY":
                if candle_prev.close < candle_prev.open and prev_strength > 0.6:
                    return False, "vela previa bajista fuerte"

            if side == "SELL":
                if candle_prev.close > candle_prev.open and prev_strength > 0.6:
                    return False, "vela previa alcista fuerte"

        # ------------------------------------------------------------
        # 6. Momentum PRO
        # ------------------------------------------------------------
        momentum = micro.get("momentum")
        if side == "BUY" and momentum == "down" and score < 3:
            return False, "momentum en contra con score débil"
        if side == "SELL" and momentum == "up" and score < 3:
            return False, "momentum en contra con score débil"

        # ------------------------------------------------------------
        # 7. Validación de TPs
        # ------------------------------------------------------------
        ok, reason = self._validate_tp_order(side, entry, [tp1, tp2, tp3])
        if not ok:
            return False, reason

        # ------------------------------------------------------------
        # 8. Validación de OB PRO
        # ------------------------------------------------------------
        ob = meta.get("ob")
        if ob:
            if "low" not in ob or "high" not in ob:
                return False, "OB inválido"

        # ------------------------------------------------------------
        # 9. Validación de Forecast PRO
        # ------------------------------------------------------------
        forecast = meta.get("forecast")
        if forecast and not isinstance(forecast, dict):
            return False, "forecast inválido"

        # ------------------------------------------------------------
        # 10. Validación de Timing PRO
        # ------------------------------------------------------------
        if timing and isinstance(timing, dict):
            if not timing.get("valid", True):
                return False, "timing inválido"

        # ------------------------------------------------------------
        # 11. Validación de Context PRO
        #     - SCALPER: NO exige tendencia 4H (acepta neutral)
        #     - SWING:   exige bullish / bearish
        # ------------------------------------------------------------
        if context and isinstance(context, dict):
            trend = context.get("trend_4h")

            # SCALPER: solo rechazamos valores raros, aceptamos None / bullish / bearish / neutral
            if mode == "SCALPER":
                if trend not in (None, "bullish", "bearish", "neutral"):
                    return False, "contexto inválido"

            # SWING: exige tendencia direccional clara
            elif mode == "SWING":
                if trend not in ("bullish", "bearish"):
                    return False, "contexto inválido (SWING sin tendencia 4H)"

            # Si no hay mode definido, mantenemos la validación original conservadora
            else:
                if trend not in (None, "bullish", "bearish"):
                    return False, "contexto inválido"

        # ------------------------------------------------------------
        # 12. Validación de Delta PRO
        # ------------------------------------------------------------
        if delta and isinstance(delta, dict):
            d = delta.get("delta")
            cd = delta.get("cumdelta")

            if d is not None and abs(d) > 5000:
                return False, "delta extremo inválido"

            if cd is not None and abs(cd) > 20000:
                return False, "cumdelta extremo inválido"

        # ------------------------------------------------------------
        # 13. Señal válida
        # ------------------------------------------------------------
        return True, "valid"


# Instancia global
execution_engine = ExecutionEnginePRO()
