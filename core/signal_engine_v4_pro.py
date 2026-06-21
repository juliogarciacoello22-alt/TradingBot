# core/signal_engine_v4.py

class SignalEngineV4:
    """
    SignalEngine V4 — Institucional + Delta PRO
    Produce:
    - side (BUY/SELL)
    - mode (SCALPER/SWING)
    - entry / stop institucionales
    - tp1, tp2, tp3 institucionales
    - score institucional
    - meta institucional completo
    """

    def __init__(self, reaction_engine):
        self.reaction = reaction_engine

    # ============================================================
    #   VALIDACIÓN INSTITUCIONAL
    # ============================================================
    def _valid_entry(self, micro):
        if not micro.get("displacement"):
            return False
        if not micro.get("momentum"):
            return False
        if micro.get("fake_displacement"):
            return False
        if micro.get("inducement") == "fake":
            return False
        if micro.get("mitigation_light"):
            return False
        return True

    # ============================================================
    #   DELTA PRO — FILTROS INSTITUCIONALES
    # ============================================================
    def _delta_filters(self, micro, delta, cumdelta, last_candle):
        disp = micro.get("displacement")

        # 1. DELTA DIRECCIONAL
        if delta is not None:
            if delta < -400 and disp == "up":
                return False
            if delta > 400 and disp == "down":
                return False

        # 2. CUMDELTA — CONTEXTO DE SESIÓN
        if cumdelta is not None:
            if cumdelta < -3000 and disp == "up":
                return False
            if cumdelta > 3000 and disp == "down":
                return False

        # 3. DELTA SHIFT
        prev = getattr(last_candle, "prev_delta", None)
        if prev is not None and delta is not None:
            shift = delta - prev
            if disp == "up" and shift < -600:
                return False
            if disp == "down" and shift > 600:
                return False

        # 4. DELTA CLIMAX
        if delta is not None and abs(delta) > 2500:
            return False

        # 5. DELTA EXHAUSTION
        if delta is not None and prev is not None:
            if abs(prev) > 1500 and abs(delta) < 150:
                return False

        # 6. DELTA DIVERGENCE
        if prev is not None and delta is not None:
            price_up = last_candle.close > last_candle.open
            delta_up = delta > prev

            if price_up and not delta_up and disp == "up":
                return False
            if not price_up and delta_up and disp == "down":
                return False

        # 7. DELTA IMBALANCE
        if delta is not None:
            if disp == "up" and delta < -800:
                return False
            if disp == "down" and delta > 800:
                return False

        return True

    # ============================================================
    #   SCALPER INSTITUCIONAL
    # ============================================================
    def _scalper(self, micro, price, meta):
        disp = micro.get("displacement")
        if not disp:
            return None

        side = "BUY" if disp == "up" else "SELL"
        reaction = self.reaction.evaluate(side, price, meta)

        if not reaction.get("reaction_ok"):
            return None

        return {
            "side": side,
            "mode": "SCALPER",
            "entry": reaction["entry"],
            "stop": reaction["stop"],
            "tp1": reaction["tp1"],
            "tp2": reaction["tp2"],
            "tp3": reaction["tp3"],
            "score": 4,
            "reason": "scalper institucional",
            "ob": reaction["ob"],
            "meta": meta
        }

    # ============================================================
    #   SWING INSTITUCIONAL
    # ============================================================
    def _swing(self, micro, price, meta, context):
        trend = context.get("trend_4h")
        if trend not in ("bullish", "bearish"):
            return None

        side = "BUY" if trend == "bullish" else "SELL"
        reaction = self.reaction.evaluate(side, price, meta)

        if not reaction.get("reaction_ok"):
            return None

        return {
            "side": side,
            "mode": "SWING",
            "entry": reaction["entry"],
            "stop": reaction["stop"],
            "tp1": reaction["tp1"],
            "tp2": reaction["tp2"],
            "tp3": reaction["tp3"],
            "score": 5,
            "reason": "swing institucional 4H",
            "ob": reaction["ob"],
            "meta": meta
        }

    # ============================================================
    #   API PRINCIPAL
    # ============================================================
    def build_signal(self, tf, micro, context, timing, delta, forecast):

        # 1. Validación institucional mínima
        if not self._valid_entry(micro):
            return None

        # 2. Timing institucional
        if isinstance(timing, dict) and not timing.get("valid", True):
            return None

        # 3. Extraer vela y cumdelta
        last_candle = tf["1m"][-1]
        cumdelta = getattr(last_candle, "cumdelta", None)

        # 4. DELTA PRO — FILTROS
        if not self._delta_filters(micro, delta, cumdelta, last_candle):
            return None

        # 5. Meta institucional
        meta = {
            "micro": micro,
            "ob": micro.get("ob"),
            "fvg": micro.get("fvg"),
            "liquidity": micro.get("liquidity"),
            "forecast": forecast,
            "delta": delta,
            "cumdelta": cumdelta,
            "context": context
        }

        price = last_candle.close

        # 6. SWING (PRIORIDAD MÁXIMA)
        swing = self._swing(micro, price, meta, context)
        if swing:
            return swing

        # 7. SCALPER (SECUNDARIO)
        scalper = self._scalper(micro, price, meta)
        if scalper:
            return scalper

        return None
