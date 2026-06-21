class BiasEngine:
    def compute_bias(self, tf):

        last_4h  = tf["4h"][-1]
        last_30m = tf["30m"][-1]
        last_5m  = tf["5m"][-1]

        # 4H
        structure = (last_4h.structure or "").lower()
        bias_4h = 1 if structure == "bullish" else -1 if structure == "bearish" else 0

        # 30M
        zones = last_30m.zones or []
        has_demand = any(z.high < last_30m.close for z in zones)
        has_supply = any(z.low  > last_30m.close for z in zones)
        bias_30m = 1 if has_demand and not has_supply else -1 if has_supply and not has_demand else 0

        # 5M
        intent = (last_5m.intent or "").lower()
        bias_5m = 1 if intent == "bullish" else -1 if intent == "bearish" else 0

        # Final
        total = (bias_4h * 2) + bias_30m + bias_5m

        if total >= 2:
            return "bullish"
        elif total <= -2:
            return "bearish"
        return "neutral"
