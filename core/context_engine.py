class ContextEngine:
    """
    CONTEXT ENGINE — BIUMOLO INSTITUTIONAL
    Produce contexto HTF para SignalEngine v4:
    - intención 5m
    - tendencia 4h
    - premium/discount 5m
    - BOS/CHOCH 5m
    """

    def __init__(self):
        pass

    def detect_intent_5m(self, candles):
        if len(candles) < 4:
            return "none"

        c2 = candles[-3]
        c3 = candles[-2]
        c4 = candles[-1]

        bos_up   = c4.close > max(c2.high, c3.high)
        bos_down = c4.close < min(c2.low,  c3.low)

        body   = abs(c4.close - c4.open)
        range_ = c4.high - c4.low
        disp_up   = body > range_ * 0.55 and c4.close > c4.open
        disp_down = body > range_ * 0.55 and c4.close < c4.open

        score_up   = bos_up + disp_up
        score_down = bos_down + disp_down

        if score_up >= 2:
            return "bullish"
        if score_down >= 2:
            return "bearish"

        return "none"

    def detect_premium_discount_5m(self, candle):
        midpoint = (candle.high + candle.low) / 2
        premium  = candle.close > midpoint
        discount = candle.close < midpoint
        return premium, discount

    def detect_structure_5m(self, candles):
        if len(candles) < 3:
            return None, None

        prev = candles[-2]
        curr = candles[-1]

        bos = None
        choch = None

        if curr.high > prev.high:
            bos = "up"
        if curr.low < prev.low:
            bos = "down"

        if curr.close > prev.open and curr.low < prev.low:
            choch = "up"
        if curr.close < prev.open and curr.high > prev.high:
            choch = "down"

        return bos, choch

    def detect_trend_4h(self, candles):
        if len(candles) < 10:
            return "neutral"

        last = candles[-1]
        prev = candles[-5]

        if last.close > prev.high:
            return "bullish"
        if last.close < prev.low:
            return "bearish"

        return "neutral"

    def build_context(self, tf):
        candles_5m = tf.get("5m", [])
        candles_4h = tf.get("4h", [])

        # Caso 1: no hay 5m → todo neutral
        if not candles_5m:
            return {
                "intent_5m": "none",
                "trend_4h": "neutral",
                "premium_5m": False,
                "discount_5m": False,
                "bos_5m": None,
                "choch_5m": None
            }

        # Caso 2: hay 5m pero no hay 4h → usamos 5m, trend neutral
        if not candles_4h:
            intent_5m = self.detect_intent_5m(candles_5m)
            premium_5m, discount_5m = self.detect_premium_discount_5m(candles_5m[-1])
            bos_5m, choch_5m = self.detect_structure_5m(candles_5m)

            return {
                "intent_5m": intent_5m,
                "trend_4h": "neutral",
                "premium_5m": premium_5m,
                "discount_5m": discount_5m,
                "bos_5m": bos_5m,
                "choch_5m": choch_5m
            }

        # Caso 3: hay 5m y 4h → contexto completo
        intent_5m = self.detect_intent_5m(candles_5m)
        premium_5m, discount_5m = self.detect_premium_discount_5m(candles_5m[-1])
        bos_5m, choch_5m = self.detect_structure_5m(candles_5m)
        trend_4h = self.detect_trend_4h(candles_4h)

        return {
            "intent_5m": intent_5m,
            "trend_4h": trend_4h,
            "premium_5m": premium_5m,
            "discount_5m": discount_5m,
            "bos_5m": bos_5m,
            "choch_5m": choch_5m
        }
