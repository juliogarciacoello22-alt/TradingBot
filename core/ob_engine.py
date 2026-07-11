# core/ob_engine.py

def _decision_log(stage, allowed, reason, detail):
    print(
        ">> OB ENGINE DECISION stage={stage} allowed={allowed} reason={reason} detail={detail}".format(
            stage=stage,
            allowed=allowed,
            reason=reason,
            detail=detail,
        )
    )

class OBEngine:
    """
    OBEngine PRO — BIUMOLO INSTITUTIONAL
    ------------------------------------
    Detecta Order Blocks institucionales:
    - OB alcista / bajista
    - Validación con displacement real
    - Validación con sweep previo
    - Validación con absorción
    - Validación con breaker shift
    - Validación con liquidez (EQH/EQL)
    - Strength institucional
    - Mitigación correcta
    - Contrato compatible con ReactionEngine PRO
    """

    def __init__(self):
        self.last_ob = None
        self.last_decision_reason = None
        self.last_decision_detail = None

    # ============================================================
    #   1. VALIDAR DISPLACEMENT INSTITUCIONAL
    # ============================================================
    def _valid_displacement(self, candle):
        if candle.range == 0:
            return None

        # cuerpo dominante → desplazamiento institucional
        if candle.body > candle.range * 0.55:
            return "up" if candle.close > candle.open else "down"

        return None

    # ============================================================
    #   2. DETECTAR OB BRUTO (SIN VALIDAR)
    # ============================================================
    def _raw_ob(self, candles):
        if len(candles) < 3:
            return None

        c1 = candles[-3]
        c2 = candles[-2]  # vela que se convierte en OB
        c3 = candles[-1]  # vela de displacement

        disp = self._valid_displacement(c3)
        if not disp:
            return None

        # OB bajista → última vela alcista antes del displacement bajista
        if disp == "down" and c2.close > c2.open:
            return {
                "type": "bearish",
                "open": c2.open,
                "low": c2.low,
                "high": c2.high,
                "origin": "micro",
                "displacement": "down"
            }

        # OB alcista → última vela bajista antes del displacement alcista
        if disp == "up" and c2.close < c2.open:
            return {
                "type": "bullish",
                "open": c2.open,
                "low": c2.low,
                "high": c2.high,
                "origin": "micro",
                "displacement": "up"
            }

        return None

    # ============================================================
    #   3. VALIDACIÓN INSTITUCIONAL COMPLETA
    # ============================================================
    def _validate_ob(self, ob, micro):
        if not ob:
            return None

        sweep      = micro.get("sweep")
        absorption = micro.get("absorption")
        breaker    = micro.get("breaker")
        liquidity  = micro.get("liquidity", {})
        mitigation = micro.get("mitigation_light")

        strength = 0

        # displacement fuerte
        if ob.get("displacement"):
            strength += 2

        # sweep previo
        if sweep:
            strength += 1

        # absorción institucional
        if absorption:
            strength += 1

        # breaker shift
        if breaker:
            strength += 1

        # liquidez institucional
        if liquidity.get("eqh") or liquidity.get("eql"):
            strength += 1

        # penalización por mitigación previa
        if mitigation:
            strength -= 2

        # asignar metadata institucional
        ob["strength"]       = strength
        ob["sweep_before"]   = sweep is not None
        ob["absorption"]     = absorption
        ob["breaker"]        = breaker
        ob["liquidity"]      = liquidity
        ob["valid"]          = strength >= 2

        return ob

    # ============================================================
    #   4. MARCAR MITIGACIÓN REAL
    # ============================================================
    def _mark_mitigation(self, ob, candle):
        if not ob:
            return ob

        if ob["type"] == "bullish":
            mitigated = candle.low <= ob["low"]
        else:
            mitigated = candle.high >= ob["high"]

        ob["mitigated"] = mitigated
        return ob

    # ============================================================
    #   5. API PRINCIPAL
    # ============================================================
    def detect_ob(self, candles, micro):
        raw = self._raw_ob(candles)
        validated = self._validate_ob(raw, micro)

        if not raw:
            detail = "candles={count}".format(count=len(candles))
            self.last_decision_reason = "raw_ob_missing"
            self.last_decision_detail = detail
            _decision_log("detect_ob", False, "raw_ob_missing", detail)
            return None

        if not validated:
            detail = "raw_type={ob_type} displacement={displacement}".format(
                ob_type=raw.get("type"),
                displacement=raw.get("displacement"),
            )
            self.last_decision_reason = "validation_failed"
            self.last_decision_detail = detail
            _decision_log("detect_ob", False, "validation_failed", detail)
            return None

        final = self._mark_mitigation(validated, candles[-1])

        detail = "type={ob_type} valid={valid} strength={strength} mitigated={mitigated}".format(
            ob_type=final.get("type"),
            valid=final.get("valid"),
            strength=final.get("strength"),
            mitigated=final.get("mitigated"),
        )
        self.last_decision_reason = "ok"
        self.last_decision_detail = detail
        _decision_log("detect_ob", True, "ok", detail)

        self.last_ob = final
        return final
