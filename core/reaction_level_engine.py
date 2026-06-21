from core.tp_engine import TPEngine


class ReactionLevelEngine:
    """
    ReactionLevelEngine PRO — Institucional + Meta
    ----------------------------------------------
    - Usa microestructura PRO
    - Usa OB desde meta
    - Usa delta / cumdelta desde meta
    - Genera entry / stop / TP1-TP3 institucionales
    """

    def __init__(self):
        self.tp_engine = TPEngine()

    # ============================================================
    #   DELTA PRO — VALIDACIONES INSTITUCIONALES
    # ============================================================
    def _delta_ok(self, side, delta, prev_delta, cumdelta):
        # 1. Delta direccional básico
        if delta is not None:
            if side == "BUY" and delta < -400:
                return False, "delta contra BUY"
            if side == "SELL" and delta > 400:
                return False, "delta contra SELL"

        # 2. Contexto de sesión (cumdelta)
        if cumdelta is not None:
            if side == "BUY" and cumdelta < -3000:
                return False, "sesión bajista fuerte"
            if side == "SELL" and cumdelta > 3000:
                return False, "sesión alcista fuerte"

        # 3. Delta shift (cambio brusco)
        if delta is not None and prev_delta is not None:
            shift = delta - prev_delta
            if side == "BUY" and shift < -600:
                return False, "delta shift contra BUY"
            if side == "SELL" and shift > 600:
                return False, "delta shift contra SELL"

        # 4. Delta climax (extremo)
        if delta is not None and abs(delta) > 2500:
            return False, "delta climax"

        # 5. Delta exhaustion (agotamiento)
        if delta is not None and prev_delta is not None:
            if abs(prev_delta) > 1500 and abs(delta) < 150:
                return False, "delta exhaustion"

        # 6. Delta imbalance fuerte
        if delta is not None:
            if side == "BUY" and delta < -800:
                return False, "delta imbalance contra BUY"
            if side == "SELL" and delta > 800:
                return False, "delta imbalance contra SELL"

        return True, "OK"

    # ============================================================
    #   1. VALIDAR OB
    # ============================================================
    def validate_ob(self, ob, side):
        try:
            if not ob or not ob.get("valid"):
                return False, "OB inválido"

            ob_type = ob.get("type")

            if side == "BUY" and ob_type != "bullish":
                return False, "OB no es alcista"

            if side == "SELL" and ob_type != "bearish":
                return False, "OB no es bajista"

            if ob.get("high") is None or ob.get("low") is None:
                return False, "OB sin rango válido"

            if ob.get("high") <= ob.get("low"):
                return False, "OB rango invertido"

            return True, "OK"

        except Exception as e:
            print("ERROR EN REACTION ENGINE (validate_ob):", e)
            return False, "error interno"

    # ============================================================
    #   2. GENERAR ENTRY / STOP
    # ============================================================
    def generate_entry_stop(self, ob, side):
        try:
            entry = ob.get("open")
            stop  = ob.get("low") if side == "BUY" else ob.get("high")

            if entry is None or stop is None:
                return None, None

            if side == "BUY" and stop >= entry:
                return None, None

            if side == "SELL" and stop <= entry:
                return None, None

            return entry, stop

        except Exception as e:
            print("ERROR EN REACTION ENGINE (entry/stop):", e)
            return None, None

    # ============================================================
    #   3. VALIDAR PROXIMIDAD
    # ============================================================
    def validate_proximity(self, price, ob):
        try:
            ob_open = ob.get("open")
            ob_high = ob.get("high")
            ob_low  = ob.get("low")

            if ob_open is None or ob_high is None or ob_low is None:
                return False, "OB inválido"

            ob_range = abs(ob_high - ob_low)
            if ob_range <= 0:
                return False, "OB sin rango"

            distance = abs(price - ob_open)
            if distance > ob_range:
                return False, "muy lejos del OB"

            return True, "OK"

        except Exception as e:
            print("ERROR EN REACTION ENGINE (proximity):", e)
            return False, "error interno"

    # ============================================================
    #   4. VALIDAR MITIGACIÓN
    # ============================================================
    def validate_mitigation(self, price, ob, side):
        try:
            ob_high = ob.get("high")
            ob_low  = ob.get("low")

            if ob_high is None or ob_low is None:
                return False, "OB inválido"

            if side == "BUY" and price <= ob_low:
                return False, "OB mitigado"

            if side == "SELL" and price >= ob_high:
                return False, "OB mitigado"

            return True, "OK"

        except Exception as e:
            print("ERROR EN REACTION ENGINE (mitigation):", e)
            return False, "error interno"

    # ============================================================
    #   5. EVALUACIÓN PRINCIPAL — META + DELTA PRO
    # ============================================================
    def evaluate(self, side, price, meta):
        try:
            micro = meta.get("micro", {})
            ob    = meta.get("ob")  # ahora OB viene desde meta

            if not ob:
                return {"reaction_ok": False, "reason": "OB ausente"}

            # 1. Validar OB
            ok, reason = self.validate_ob(ob, side)
            if not ok:
                return {"reaction_ok": False, "reason": reason}

            # 2. Validar mitigación
            ok, reason = self.validate_mitigation(price, ob, side)
            if not ok:
                return {"reaction_ok": False, "reason": reason}

            # 3. Validar proximidad
            ok, reason = self.validate_proximity(price, ob)
            if not ok:
                return {"reaction_ok": False, "reason": reason}

            # 4. Delta PRO desde meta
            delta      = meta.get("delta")
            prev_delta = meta.get("prev_delta")
            cumdelta   = meta.get("cumdelta")

            ok, reason = self._delta_ok(side, delta, prev_delta, cumdelta)
            if not ok:
                return {"reaction_ok": False, "reason": reason}

            # 5. Entry / Stop institucional
            entry, stop = self.generate_entry_stop(ob, side)
            if entry is None or stop is None:
                return {"reaction_ok": False, "reason": "entry/stop inválidos"}

            # 6. TP institucional (TPEngine PRO)
            tp1, tp2, tp3 = self.tp_engine.generate_tp(side, micro, entry, stop)
            if tp1 is None:
                return {"reaction_ok": False, "reason": "TP1 inválido"}

            return {
                "reaction_ok": True,
                "reason": "OK",
                "entry": entry,
                "stop": stop,
                "tp1": tp1,
                "tp2": tp2,
                "tp3": tp3,
                "ob": ob
            }

        except Exception as e:
            print("ERROR EN REACTION ENGINE (evaluate):", e)
            return {
                "reaction_ok": False,
                "reason": "error interno",
                "entry": None,
                "stop": None,
                "tp1": None,
                "tp2": None,
                "tp3": None
            }


reaction_engine = ReactionLevelEngine()
