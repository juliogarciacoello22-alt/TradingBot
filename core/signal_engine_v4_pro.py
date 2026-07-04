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
        self.last_build_signal_reason = None
        self.last_valid_entry_reason = None

    def _log_check(self, name, status, reason=None, detail=None):
        line = f">> SIGNAL CHECK name={name} status={'PASS' if status else 'FAIL'}"
        if reason is not None:
            line += f" reason={reason}"
        if detail is not None:
            line += f" detail={detail}"
        print(line)

    def _log_result(self, signal, reason):
        self.last_build_signal_reason = reason
        print(
            ">> BUILD_SIGNAL RESULT signal_is_none={is_none} reason={reason}".format(
                is_none=signal is None,
                reason=reason,
            )
        )

    # ============================================================
    #   VALIDACIÓN INSTITUCIONAL
    # ============================================================
    def _valid_entry(self, micro):
        self.last_valid_entry_reason = None
        if not micro.get("displacement"):
            self.last_valid_entry_reason = "missing_displacement"
            self._log_check("valid_entry.displacement", False, reason="missing_displacement")
            return False
        self._log_check("valid_entry.displacement", True, reason="displacement_present", detail=repr(micro.get("displacement")))

        if not micro.get("momentum"):
            self.last_valid_entry_reason = "missing_momentum"
            self._log_check("valid_entry.momentum", False, reason="missing_momentum")
            return False
        self._log_check("valid_entry.momentum", True, reason="momentum_present", detail=repr(micro.get("momentum")))

        if micro.get("fake_displacement"):
            self.last_valid_entry_reason = "fake_displacement_true"
            self._log_check("valid_entry.fake_displacement", False, reason="fake_displacement_true")
            return False
        self._log_check("valid_entry.fake_displacement", True, reason="fake_displacement_false")

        if micro.get("inducement") == "fake":
            self.last_valid_entry_reason = "fake_inducement"
            self._log_check("valid_entry.inducement", False, reason="fake_inducement")
            return False
        self._log_check("valid_entry.inducement", True, reason="inducement_ok", detail=repr(micro.get("inducement")))

        if micro.get("mitigation_light"):
            self.last_valid_entry_reason = "mitigation_light_true"
            self._log_check("valid_entry.mitigation_light", False, reason="mitigation_light_true")
            return False
        self._log_check("valid_entry.mitigation_light", True, reason="mitigation_light_false")

        self.last_valid_entry_reason = "entry_filters_passed"
        self._log_check("valid_entry", True, reason="entry_filters_passed")
        return True

    # ============================================================
    #   DELTA PRO — FILTROS INSTITUCIONALES
    # ============================================================
    def _delta_filters(self, micro, delta, cumdelta, last_candle):
        disp = micro.get("displacement")

        # 1. DELTA DIRECCIONAL
        if delta is not None:
            if delta < -400 and disp == "up":
                self._log_check("delta_filters.directional", False, reason="delta_conflict_up", detail=f"delta={delta} disp={disp}")
                return False
            if delta > 400 and disp == "down":
                self._log_check("delta_filters.directional", False, reason="delta_conflict_down", detail=f"delta={delta} disp={disp}")
                return False
        self._log_check("delta_filters.directional", True, reason="directional_ok", detail=f"delta={delta} disp={disp}")

        # 2. CUMDELTA — CONTEXTO DE SESIÓN
        if cumdelta is not None:
            if cumdelta < -3000 and disp == "up":
                self._log_check("delta_filters.cumdelta", False, reason="cumdelta_conflict_up", detail=f"cumdelta={cumdelta} disp={disp}")
                return False
            if cumdelta > 3000 and disp == "down":
                self._log_check("delta_filters.cumdelta", False, reason="cumdelta_conflict_down", detail=f"cumdelta={cumdelta} disp={disp}")
                return False
        self._log_check("delta_filters.cumdelta", True, reason="cumdelta_ok", detail=f"cumdelta={cumdelta} disp={disp}")

        # 3. DELTA SHIFT
        prev = getattr(last_candle, "prev_delta", None)
        if prev is not None and delta is not None:
            shift = delta - prev
            if disp == "up" and shift < -600:
                self._log_check("delta_filters.shift", False, reason="negative_shift_up", detail=f"delta={delta} prev={prev} shift={shift}")
                return False
            if disp == "down" and shift > 600:
                self._log_check("delta_filters.shift", False, reason="positive_shift_down", detail=f"delta={delta} prev={prev} shift={shift}")
                return False
            self._log_check("delta_filters.shift", True, reason="shift_ok", detail=f"delta={delta} prev={prev} shift={shift}")
        else:
            self._log_check("delta_filters.shift", True, reason="shift_not_applicable", detail=f"delta={delta} prev={prev}")

        # 4. DELTA CLIMAX
        if delta is not None and abs(delta) > 2500:
            self._log_check("delta_filters.climax", False, reason="delta_climax", detail=f"delta={delta}")
            return False
        self._log_check("delta_filters.climax", True, reason="climax_ok", detail=f"delta={delta}")

        # 5. DELTA EXHAUSTION
        if delta is not None and prev is not None:
            if abs(prev) > 1500 and abs(delta) < 150:
                self._log_check("delta_filters.exhaustion", False, reason="delta_exhaustion", detail=f"delta={delta} prev={prev}")
                return False
            self._log_check("delta_filters.exhaustion", True, reason="exhaustion_ok", detail=f"delta={delta} prev={prev}")
        else:
            self._log_check("delta_filters.exhaustion", True, reason="exhaustion_not_applicable", detail=f"delta={delta} prev={prev}")

        # 6. DELTA DIVERGENCE
        if prev is not None and delta is not None:
            price_up = last_candle.close > last_candle.open
            delta_up = delta > prev

            if price_up and not delta_up and disp == "up":
                self._log_check("delta_filters.divergence", False, reason="bullish_divergence_conflict", detail=f"price_up={price_up} delta_up={delta_up} disp={disp}")
                return False
            if not price_up and delta_up and disp == "down":
                self._log_check("delta_filters.divergence", False, reason="bearish_divergence_conflict", detail=f"price_up={price_up} delta_up={delta_up} disp={disp}")
                return False
            self._log_check("delta_filters.divergence", True, reason="divergence_ok", detail=f"price_up={price_up} delta_up={delta_up} disp={disp}")
        else:
            self._log_check("delta_filters.divergence", True, reason="divergence_not_applicable", detail=f"delta={delta} prev={prev}")

        # 7. DELTA IMBALANCE
        if delta is not None:
            if disp == "up" and delta < -800:
                self._log_check("delta_filters.imbalance", False, reason="imbalance_conflict_up", detail=f"delta={delta} disp={disp}")
                return False
            if disp == "down" and delta > 800:
                self._log_check("delta_filters.imbalance", False, reason="imbalance_conflict_down", detail=f"delta={delta} disp={disp}")
                return False
        self._log_check("delta_filters.imbalance", True, reason="imbalance_ok", detail=f"delta={delta} disp={disp}")

        self._log_check("delta_filters", True, reason="all_delta_filters_passed")
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
        self.last_build_signal_reason = None
        self.last_valid_entry_reason = None

        # 1. Validación institucional mínima
        if not self._valid_entry(micro):
            self._log_result(None, "valid_entry_failed")
            return None

        # 2. Timing institucional
        if isinstance(timing, dict) and not timing.get("valid", True):
            self._log_check("timing", False, reason=timing.get("reason", "timing_invalid"), detail=repr(timing))
            self._log_result(None, "timing_invalid")
            return None
        if isinstance(timing, dict):
            self._log_check("timing", True, reason="timing_valid", detail=repr(timing))
        else:
            self._log_check("timing", True, reason="timing_not_applicable", detail=repr(timing))

        # 3. Extraer vela y cumdelta
        last_candle = tf["1m"][-1]
        cumdelta = getattr(last_candle, "cumdelta", None)
        self._log_check("last_candle", True, reason="last_candle_loaded", detail=f"close={last_candle.close} open={last_candle.open} cumdelta={cumdelta}")

        # 4. DELTA PRO — FILTROS
        if not self._delta_filters(micro, delta, cumdelta, last_candle):
            self._log_result(None, "delta_filters_failed")
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
        self._log_check(
            "meta",
            True,
            reason="meta_built",
            detail=(
                f"ob_present={bool(micro.get('ob'))} "
                f"fvg_present={bool(micro.get('fvg'))} "
                f"liquidity_present={bool(micro.get('liquidity'))} "
                f"forecast_present={bool(forecast)} "
                f"context_present={bool(context)}"
            ),
        )

        price = last_candle.close
        self._log_check("price", True, reason="price_loaded", detail=f"price={price}")

        # 6. SWING (PRIORIDAD MÁXIMA)
        swing = self._swing(micro, price, meta, context)
        if swing:
            self._log_check(
                "swing",
                True,
                reason="swing_generated",
                detail=repr(
                    {
                        "side": swing.get("side"),
                        "mode": swing.get("mode"),
                        "entry": swing.get("entry"),
                        "stop": swing.get("stop"),
                        "tp1": swing.get("tp1"),
                        "tp2": swing.get("tp2"),
                        "tp3": swing.get("tp3"),
                    }
                ),
            )
            self._log_result(swing, "swing_generated")
            return swing
        self._log_check(
            "swing",
            False,
            reason="swing_returned_none",
            detail=f"trend_4h={context.get('trend_4h') if isinstance(context, dict) else None}",
        )

        # 7. SCALPER (SECUNDARIO)
        scalper = self._scalper(micro, price, meta)
        if scalper:
            self._log_check(
                "scalper",
                True,
                reason="scalper_generated",
                detail=repr(
                    {
                        "side": scalper.get("side"),
                        "mode": scalper.get("mode"),
                        "entry": scalper.get("entry"),
                        "stop": scalper.get("stop"),
                        "tp1": scalper.get("tp1"),
                        "tp2": scalper.get("tp2"),
                        "tp3": scalper.get("tp3"),
                    }
                ),
            )
            self._log_result(scalper, "scalper_generated")
            return scalper
        self._log_check(
            "scalper",
            False,
            reason="scalper_returned_none",
            detail=f"displacement={micro.get('displacement')}",
        )

        self._log_result(None, "no_swing_no_scalper")
        return None
