class IntentScoreEngine:
    """
    IntentScoreEngine Institucional
    -------------------------------
    Produce un score de intención coherente con el contrato:

    signal = {
        "direction": "long/short",
        "entry": float,
        "stop": float,
        "tps": [...],
        "meta": {
            "micro":   {...},
            "context": {...},
            "timing":  {...},
            "risk":    {...},
            "intent_score": int,
            "intent_reasons": [...]
        }
    }
    """

    def __init__(self):
        pass

    # ============================================================
    #   1. OB — EL FACTOR MÁS IMPORTANTE
    # ============================================================
    def score_ob(self, ob_intent):
        try:
            if not ob_intent or not ob_intent.get("valid"):
                return 0

            strength = ob_intent.get("strength", 0)

            if strength >= 2:
                return 3  # OB fuerte
            if strength == 1:
                return 2  # OB normal
            return 1       # OB débil

        except Exception as e:
            print("ERROR EN INTENT SCORE (OB):", e)
            return 0

    # ============================================================
    #   2. FVG — DESACTIVADO (NO SUMA)
    # ============================================================
    def score_fvg(self, fvg_intent):
        return 0

    # ============================================================
    #   3. SWING / CHOCH — CAMBIO DE ESTRUCTURA
    # ============================================================
    def score_swing(self, swing_intent):
        try:
            if not swing_intent or not swing_intent.get("valid"):
                return 0
            return 2  # CHOCH real
        except Exception as e:
            print("ERROR EN INTENT SCORE (SWING):", e)
            return 0

    # ============================================================
    #   4. CONTEXTO — EXPANSIÓN / COMPRESIÓN
    # ============================================================
    def score_context(self, context_intent):
        try:
            if not context_intent or not context_intent.get("valid"):
                return 0

            score = context_intent.get("score", 0)

            if score == 1:
                return 2  # expansión
            return 1      # compresión

        except Exception as e:
            print("ERROR EN INTENT SCORE (CONTEXT):", e)
            return 0

    # ============================================================
    #   5. TIMING — MOMENTUM + DISPLACEMENT
    # ============================================================
    def score_timing(self, timing_intent):
        try:
            if not timing_intent or not timing_intent.get("valid"):
                return 0

            score = timing_intent.get("score", 0)

            if score >= 1:
                return 2  # momentum + displacement
            return 1

        except Exception as e:
            print("ERROR EN INTENT SCORE (TIMING):", e)
            return 0

    # ============================================================
    #   6. RISK — RIESGO INSTITUCIONAL
    # ============================================================
    def score_risk(self, risk_intent):
        try:
            if not risk_intent or not risk_intent.get("valid"):
                return 0
            return 1
        except Exception as e:
            print("ERROR EN INTENT SCORE (RISK):", e)
            return 0

    # ============================================================
    #   7. TOTAL SCORE
    # ============================================================
    def total_score(self, ob, fvg, swing, ctx, timing, risk):
        try:
            return (
                self.score_ob(ob)
                + self.score_fvg(fvg)
                + self.score_swing(swing)
                + self.score_context(ctx)
                + self.score_timing(timing)
                + self.score_risk(risk)
            )
        except Exception as e:
            print("ERROR EN INTENT SCORE (total_score):", e)
            return 0

    # ============================================================
    #   8. MÉTODO PRINCIPAL — CONTRATO INSTITUCIONAL
    # ============================================================
    def compute(self, tf, micro, pipeline_signal=None):
        try:
            ob_intent     = micro.get("ob_intent")
            fvg_intent    = micro.get("fvg_intent")
            swing_intent  = micro.get("swing_intent")
            ctx_intent    = micro.get("context_intent")
            timing_intent = micro.get("timing_intent")
            risk_intent   = micro.get("risk_intent")

            score = self.total_score(
                ob_intent,
                fvg_intent,
                swing_intent,
                ctx_intent,
                timing_intent,
                risk_intent
            )

            reasons = []
            if ob_intent and ob_intent.get("valid"): reasons.append("OB")
            if swing_intent and swing_intent.get("valid"): reasons.append("SWING")
            if ctx_intent and ctx_intent.get("valid"): reasons.append("CONTEXT")
            if timing_intent and timing_intent.get("valid"): reasons.append("TIMING")
            if risk_intent and risk_intent.get("valid"): reasons.append("RISK OK")

            return score, reasons

        except Exception as e:
            print("ERROR EN INTENT SCORE (compute):", e)
            return 0, ["error interno"]


intent_score_engine = IntentScoreEngine()
