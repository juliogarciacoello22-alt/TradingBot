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
        self.last_reaction_stage = None
        self.last_reaction_reason = None
        self.last_reaction_summary = None

    def _reset_reaction_audit(self):
        self.last_reaction_stage = None
        self.last_reaction_reason = None
        self.last_reaction_summary = None

    def _set_reaction_audit(self, stage, reason, summary=None):
        self.last_reaction_stage = stage
        self.last_reaction_reason = reason
        self.last_reaction_summary = summary if summary is not None else "{stage}|{reason}".format(
            stage=stage,
            reason=reason,
        )

    def _log_reaction_eval_audit_start(self, side, price):
        print(">> REACTION EVAL AUDIT START side={side} price={price}".format(
            side=side,
            price=price,
        ))

    def _log_reaction_eval_audit_input(self, side, price, meta):
        micro = meta.get("micro", {}) if isinstance(meta, dict) else {}
        context = meta.get("context", {}) if isinstance(meta, dict) else {}
        print(
            ">> REACTION EVAL AUDIT INPUT side={side} price={price} ob_present={ob_present} liquidity_present={liquidity_present} forecast_present={forecast_present} micro_present={micro_present} displacement={displacement} momentum={momentum} trend_4h={trend_4h} delta={delta} cumdelta={cumdelta}".format(
                side=side,
                price=price,
                ob_present=bool(meta.get("ob")) if isinstance(meta, dict) else False,
                liquidity_present=bool(meta.get("liquidity")) if isinstance(meta, dict) else False,
                forecast_present=bool(meta.get("forecast")) if isinstance(meta, dict) else False,
                micro_present=bool(micro),
                displacement=micro.get("displacement"),
                momentum=micro.get("momentum"),
                trend_4h=(context or {}).get("trend_4h") if isinstance(context, dict) else None,
                delta=meta.get("delta") if isinstance(meta, dict) else None,
                cumdelta=meta.get("cumdelta") if isinstance(meta, dict) else None,
            )
        )

    def _log_reaction_eval_audit_step(self, stage, status, reason, detail):
        print(
            ">> REACTION EVAL AUDIT STEP stage={stage} status={status} reason={reason} detail={detail}".format(
                stage=stage,
                status=status,
                reason=reason,
                detail=detail,
            )
        )

    def _log_reaction_eval_audit_outcome(self, result):
        print(
            ">> REACTION EVAL AUDIT OUTCOME result={result} stage={stage} reason={reason}".format(
                result=result,
                stage=self.last_reaction_stage,
                reason=self.last_reaction_reason,
            )
        )

    def _log_reaction_eval_audit_success(self, side, entry, stop, tp1):
        rr = None
        try:
            risk = abs(entry - stop) if entry is not None and stop is not None else None
            reward = abs(tp1 - entry) if tp1 is not None and entry is not None else None
            rr = None if risk in (None, 0) or reward is None else round(reward / risk, 4)
        except Exception:
            rr = None
        print(
            ">> REACTION EVAL AUDIT SUCCESS side={side} entry={entry} stop={stop} tp1={tp1} rr={rr}".format(
                side=side,
                entry=entry,
                stop=stop,
                tp1=tp1,
                rr=rr,
            )
        )

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
            self._reset_reaction_audit()
            self._log_reaction_eval_audit_start(side, price)
            self._log_reaction_eval_audit_input(side, price, meta)

            micro = meta.get("micro", {})
            ob    = meta.get("ob")  # ahora OB viene desde meta

            if not ob:
                self._set_reaction_audit("EVALUATE.ob", "ob_missing", "reaction_ok=false|ob_missing")
                self._log_reaction_eval_audit_step("EVALUATE.ob", "FAIL", "ob_missing", "ob_present=False")
                self._log_reaction_eval_audit_outcome("failed")
                return {"reaction_ok": False, "reason": "OB ausente"}

            self._log_reaction_eval_audit_step("EVALUATE.ob", "PASS", "ob_present", "ob_type={ob_type}".format(ob_type=ob.get("type")))

            # 1. Validar OB
            ok, reason = self.validate_ob(ob, side)
            if not ok:
                self._set_reaction_audit("EVALUATE.validate_ob", reason, "reaction_ok=false|{reason}".format(reason=reason))
                self._log_reaction_eval_audit_step("EVALUATE.validate_ob", "FAIL", reason, "side={side} ob={ob}".format(side=side, ob=repr(ob)))
                self._log_reaction_eval_audit_outcome("failed")
                return {"reaction_ok": False, "reason": reason}
            self._log_reaction_eval_audit_step("EVALUATE.validate_ob", "PASS", reason, "side={side}".format(side=side))

            # 2. Validar mitigación
            ok, reason = self.validate_mitigation(price, ob, side)
            if not ok:
                self._set_reaction_audit("EVALUATE.validate_mitigation", reason, "reaction_ok=false|{reason}".format(reason=reason))
                self._log_reaction_eval_audit_step("EVALUATE.validate_mitigation", "FAIL", reason, "price={price}".format(price=price))
                self._log_reaction_eval_audit_outcome("failed")
                return {"reaction_ok": False, "reason": reason}
            self._log_reaction_eval_audit_step("EVALUATE.validate_mitigation", "PASS", reason, "price={price}".format(price=price))

            # 3. Validar proximidad
            ok, reason = self.validate_proximity(price, ob)
            if not ok:
                self._set_reaction_audit("EVALUATE.validate_proximity", reason, "reaction_ok=false|{reason}".format(reason=reason))
                self._log_reaction_eval_audit_step("EVALUATE.validate_proximity", "FAIL", reason, "price={price}".format(price=price))
                self._log_reaction_eval_audit_outcome("failed")
                return {"reaction_ok": False, "reason": reason}
            self._log_reaction_eval_audit_step("EVALUATE.validate_proximity", "PASS", reason, "price={price}".format(price=price))

            # 4. Delta PRO desde meta
            delta      = meta.get("delta")
            prev_delta = meta.get("prev_delta")
            cumdelta   = meta.get("cumdelta")

            ok, reason = self._delta_ok(side, delta, prev_delta, cumdelta)
            if not ok:
                self._set_reaction_audit("EVALUATE.delta", reason, "reaction_ok=false|{reason}".format(reason=reason))
                self._log_reaction_eval_audit_step(
                    "EVALUATE.delta",
                    "FAIL",
                    reason,
                    "delta={delta} prev_delta={prev_delta} cumdelta={cumdelta}".format(
                        delta=delta,
                        prev_delta=prev_delta,
                        cumdelta=cumdelta,
                    ),
                )
                self._log_reaction_eval_audit_outcome("failed")
                return {"reaction_ok": False, "reason": reason}
            self._log_reaction_eval_audit_step(
                "EVALUATE.delta",
                "PASS",
                reason,
                "delta={delta} prev_delta={prev_delta} cumdelta={cumdelta}".format(
                    delta=delta,
                    prev_delta=prev_delta,
                    cumdelta=cumdelta,
                ),
            )

            # 5. Entry / Stop institucional
            entry, stop = self.generate_entry_stop(ob, side)
            if entry is None or stop is None:
                self._set_reaction_audit("EVALUATE.entry_stop", "entry/stop inválidos", "reaction_ok=false|entry/stop inválidos")
                self._log_reaction_eval_audit_step("EVALUATE.entry_stop", "FAIL", "entry/stop inválidos", "side={side} ob_open={open} ob_high={high} ob_low={low}".format(
                    side=side,
                    open=ob.get("open"),
                    high=ob.get("high"),
                    low=ob.get("low"),
                ))
                self._log_reaction_eval_audit_outcome("failed")
                return {"reaction_ok": False, "reason": "entry/stop inválidos"}
            self._log_reaction_eval_audit_step("EVALUATE.entry_stop", "PASS", "entry_stop_computed", "entry={entry} stop={stop}".format(entry=entry, stop=stop))

            # 6. TP institucional (TPEngine PRO)
            tp1, tp2, tp3 = self.tp_engine.generate_tp(side, micro, entry, stop)
            if tp1 is None:
                self._set_reaction_audit("EVALUATE.tp", "TP1 inválido", "reaction_ok=false|TP1 inválido")
                self._log_reaction_eval_audit_step("EVALUATE.tp", "FAIL", "TP1 inválido", "entry={entry} stop={stop}".format(entry=entry, stop=stop))
                self._log_reaction_eval_audit_outcome("failed")
                return {"reaction_ok": False, "reason": "TP1 inválido"}
            self._log_reaction_eval_audit_step(
                "EVALUATE.tp",
                "PASS",
                "tp_generated",
                "tp1={tp1} tp2={tp2} tp3={tp3}".format(tp1=tp1, tp2=tp2, tp3=tp3),
            )

            self._set_reaction_audit("EVALUATE.success", "OK", "reaction_ok=true|OK")
            self._log_reaction_eval_audit_success(side, entry, stop, tp1)
            self._log_reaction_eval_audit_outcome("success")
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
            self._set_reaction_audit("EVALUATE.exception", "error interno", "reaction_ok=false|error interno")
            self._log_reaction_eval_audit_step("EVALUATE.exception", "FAIL", "error interno", repr(e))
            self._log_reaction_eval_audit_outcome("failed")
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
