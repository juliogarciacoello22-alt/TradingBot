# core/risk_engine_v4_pro.py

class RiskEngine:
    """
    RiskEngine v4 PRO — Institucional
    Evalúa:
    - microestructura PRO
    - OB institucional
    - forecast institucional
    - contexto 4H
    - delta PRO
    - cumdelta PRO
    - mode (SCALPER/SWING)
    - score institucional
    """

    def __init__(self):
        pass

    # ============================================================
    #   MICROSTRUCTURE RISKS
    # ============================================================
    def volatility_risk(self, micro):
        vol = micro.get("volatility")

        if vol == "compression":
            return {"valid": True, "score": -1, "reason": "compresión"}

        if vol == "normal":
            return {"valid": True, "score": 0, "reason": "normal"}

        if vol == "expansion":
            return {"valid": True, "score": 1, "reason": "expansión"}

        return {"valid": True, "score": 0, "reason": "sin datos"}

    def wick_risk(self, micro):
        wu = micro.get("wick_up", 0)
        wd = micro.get("wick_down", 0)
        body = micro.get("body", 1)

        if body == 0:
            body = 1

        if wu > body * 3 or wd > body * 3:
            return {"valid": False, "score": -3, "reason": "wick extremo"}

        if wu > body * 1.5 or wd > body * 1.5:
            return {"valid": True, "score": -1, "reason": "wick grande"}

        return {"valid": True, "score": 0, "reason": "normal"}

    def absorption_risk(self, micro, side):
        a = micro.get("absorption")

        if not a:
            return {"valid": True, "score": 0, "reason": "sin absorción"}

        if side == "BUY" and a == "sell":
            return {"valid": False, "score": -3, "reason": "absorción en contra"}

        if side == "SELL" and a == "buy":
            return {"valid": False, "score": -3, "reason": "absorción en contra"}

        return {"valid": True, "score": 1, "reason": "absorción a favor"}

    def fake_displacement_risk(self, micro):
        if micro.get("fake_displacement"):
            return {"valid": False, "score": -3, "reason": "fake displacement"}
        return {"valid": True, "score": 0, "reason": "real"}

    def liquidity_risk(self, micro, side):
        liq = micro.get("liquidity", {})
        eqh = liq.get("eqh")
        eql = liq.get("eql")

        if side == "BUY":
            if eqh:
                return {"valid": True, "score": -1, "reason": "EQH encima (riesgo)"}
            if eql:
                return {"valid": True, "score": 1, "reason": "EQL debajo (favorable)"}

        if side == "SELL":
            if eql:
                return {"valid": True, "score": -1, "reason": "EQL debajo (riesgo)"}
            if eqh:
                return {"valid": True, "score": 1, "reason": "EQH encima (favorable)"}

        return {"valid": True, "score": 0, "reason": "neutral"}

    def premium_discount_risk(self, micro, side):
        if side == "BUY" and micro.get("discount"):
            return {"valid": True, "score": 1, "reason": "discount favorable"}

        if side == "SELL" and micro.get("premium"):
            return {"valid": True, "score": 1, "reason": "premium favorable"}

        return {"valid": True, "score": 0, "reason": "neutral"}

    def breaker_risk(self, micro):
        if micro.get("breaker"):
            return {"valid": True, "score": 1, "reason": "breaker institucional"}
        return {"valid": True, "score": 0, "reason": "sin breaker"}

    def fvg_risk(self, micro):
        if micro.get("fvg"):
            return {"valid": True, "score": 1, "reason": "FVG institucional"}
        return {"valid": True, "score": 0, "reason": "sin FVG"}

    # ============================================================
    #   OB RISK
    # ============================================================
    def ob_risk(self, ob):
        if not ob:
            return {"valid": False, "score": -3, "reason": "OB ausente"}

        if ob.get("mitigated"):
            return {"valid": False, "score": -3, "reason": "OB mitigado"}

        strength = ob.get("strength", 0)

        if strength < 2:
            return {"valid": True, "score": -1, "reason": "OB débil"}

        return {"valid": True, "score": 1, "reason": "OB fuerte"}

    # ============================================================
    #   FORECAST RISK
    # ============================================================
    def forecast_risk(self, forecast, side):
        if not forecast:
            return {"valid": True, "score": 0, "reason": "sin forecast"}

        bias = forecast.get("bias")

        if side == "BUY" and bias == "bearish":
            return {"valid": True, "score": -1, "reason": "forecast bearish"}

        if side == "SELL" and bias == "bullish":
            return {"valid": True, "score": -1, "reason": "forecast bullish"}

        return {"valid": True, "score": 1, "reason": "forecast favorable"}

    # ============================================================
    #   CONTEXT RISK (4H)
    # ============================================================
    def context_risk(self, context, side):
        if not context:
            return {"valid": True, "score": 0, "reason": "sin contexto"}

        trend = context.get("trend_4h")

        if side == "BUY" and trend == "bearish":
            return {"valid": True, "score": -2, "reason": "4H bajista"}

        if side == "SELL" and trend == "bullish":
            return {"valid": True, "score": -2, "reason": "4H alcista"}

        return {"valid": True, "score": 1, "reason": "4H favorable"}

    # ============================================================
    #   DELTA RISK
    # ============================================================
    def delta_risk(self, delta, cumdelta):
        if delta is None:
            return {"valid": True, "score": 0, "reason": "sin delta"}

        if abs(delta) > 2500:
            return {"valid": False, "score": -3, "reason": "delta extremo"}

        if cumdelta is not None and abs(cumdelta) > 20000:
            return {"valid": False, "score": -3, "reason": "cumdelta extremo"}

        return {"valid": True, "score": 0, "reason": "delta normal"}

    # ============================================================
    #   EVALUACIÓN FINAL
    # ============================================================
    def evaluate(self, micro, side, meta=None):
        meta = meta or {}

        ob        = meta.get("ob")
        forecast  = meta.get("forecast")
        context   = meta.get("context")
        delta     = meta.get("delta")
        cumdelta  = meta.get("cumdelta")

        risks = [
            self.volatility_risk(micro),
            self.wick_risk(micro),
            self.absorption_risk(micro, side),
            self.fake_displacement_risk(micro),
            self.liquidity_risk(micro, side),
            self.premium_discount_risk(micro, side),
            self.breaker_risk(micro),
            self.fvg_risk(micro),
            self.ob_risk(ob),
            self.forecast_risk(forecast, side),
            self.context_risk(context, side),
            self.delta_risk(delta, cumdelta)
        ]

        total = sum(r["score"] for r in risks)

        for r in risks:
            if not r["valid"]:
                return {
                    "valid": False,
                    "risk_score": total,
                    "reason": r["reason"],
                    "details": risks
                }

        return {
            "valid": True,
            "risk_score": total,
            "reason": "riesgo aceptable",
            "details": risks
        }
