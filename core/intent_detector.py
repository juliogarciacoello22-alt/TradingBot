class IntentDetector:
    """
    IntentDetector Institucional
    ----------------------------
    Este módulo NO recalcula microestructura.
    Solo interpreta señales institucionales ya generadas por:
    - MicrostructureEngine
    - BOSEngine
    - OBEngine
    - AbsorptionDetector
    - MomentumDetector
    - InducementDetector
    """

    def __init__(self):
        pass

    # ============================================================
    #   1. INTENCIÓN HTF (5m) — DIRECCIÓN INSTITUCIONAL
    # ============================================================
    def detect_intent(self, candles):
        """
        Intención HTF basada en:
        - BOS institucional
        - displacement institucional
        - continuidad institucional
        """

        if len(candles) < 4:
            return {"intent": "none"}

        c2 = candles[-3]
        c3 = candles[-2]
        c4 = candles[-1]

        # BOS institucional
        bos_up   = c4.close > max(c2.high, c3.high)
        bos_down = c4.close < min(c2.low,  c3.low)

        # displacement institucional
        body = abs(c4.close - c4.open)
        range_ = c4.high - c4.low
        disp_up   = body > range_ * 0.55 and c4.close > c4.open
        disp_down = body > range_ * 0.55 and c4.close < c4.open

        score_up   = bos_up + disp_up
        score_down = bos_down + disp_down

        if score_up >= 2:
            return {"intent": "bullish"}

        if score_down >= 2:
            return {"intent": "bearish"}

        return {"intent": "none"}

    # ============================================================
    #   2. INTENCIÓN MICRO — INTERPRETACIÓN INSTITUCIONAL
    # ============================================================
    def evaluate(self, micro):
        """
        Interpreta microestructura institucional:
        - displacement
        - sweep
        - BOS/CHOCH
        - breaker
        - momentum
        - absorción
        - inducement
        - volatilidad
        """

        intents = []

        # displacement
        disp = micro.get("displacement")
        if disp == "up":
            intents.append({"valid": True, "side": "BUY", "score": 1})
        elif disp == "down":
            intents.append({"valid": True, "side": "SELL", "score": 1})

        # sweep
        sweep = micro.get("sweep")
        if sweep == "up":
            intents.append({"valid": True, "side": "SELL", "score": 2})
        elif sweep == "down":
            intents.append({"valid": True, "side": "BUY", "score": 2})

        # BOS / CHOCH
        bos = micro.get("bos")
        choch = micro.get("choch")
        if bos == "up" or choch == "up":
            intents.append({"valid": True, "side": "BUY", "score": 2})
        elif bos == "down" or choch == "down":
            intents.append({"valid": True, "side": "SELL", "score": 2})

        # breaker
        breaker = micro.get("breaker")
        if breaker:
            if breaker["type"] == "bullish":
                intents.append({"valid": True, "side": "BUY", "score": breaker.get("strength", 1)})
            elif breaker["type"] == "bearish":
                intents.append({"valid": True, "side": "SELL", "score": breaker.get("strength", 1)})

        # momentum
        mom = micro.get("momentum")
        if mom == "up":
            intents.append({"valid": True, "side": "BUY", "score": 1})
        elif mom == "down":
            intents.append({"valid": True, "side": "SELL", "score": 1})

        # absorción
        abs_ = micro.get("absorption")
        if abs_ == "buy":
            intents.append({"valid": True, "side": "BUY", "score": 2})
        elif abs_ == "sell":
            intents.append({"valid": True, "side": "SELL", "score": 2})

        # inducement
        if micro.get("inducement"):
            if disp == "up":
                intents.append({"valid": True, "side": "BUY", "score": 1})
            elif disp == "down":
                intents.append({"valid": True, "side": "SELL", "score": 1})

        # volatilidad
        if micro.get("expansion"):
            intents.append({"valid": True, "side": None, "score": 1})

        total_score = sum(i["score"] for i in intents)
        valid = any(i["valid"] for i in intents)

        return {
            "valid": valid,
            "score": total_score,
            "intents": intents
        }
