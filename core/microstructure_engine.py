# core/microstructure_engine.py

def _decision_log(stage, allowed, reason, detail):
    print(
        ">> MICROSTRUCTURE DECISION stage={stage} allowed={allowed} reason={reason} detail={detail}".format(
            stage=stage,
            allowed=allowed,
            reason=reason,
            detail=detail,
        )
    )

class MicrostructureEngine:
    """
    MicrostructureEngine PRO — Institucional + Delta PRO
    Produce:
    - displacement PRO (delta-confirmado)
    - sweep real
    - momentum PRO (delta-acelerado)
    - inducement PRO (delta-absorption)
    - mitigation_light
    - fake_displacement PRO (delta-contradiction)
    - absorption PRO (delta absorption)
    - breaker PRO (delta shift)
    - liquidity institucional (EQH/EQL)
    - fvg institucional
    - premium / discount institucional
    - swings institucionales
    - compression / expansion institucional
    """

    def __init__(self):
        self.prev = None
        self.prev2 = None

    # ============================================================
    #   DISPLACEMENT PRO (delta confirmado)
    # ============================================================
    def _displacement_with_reason(self, c, delta):
        body = abs(c.close - c.open)
        rng = c.high - c.low
        threshold = 0.55
        body_ratio = None if rng == 0 else body / rng
        diagnostics = {
            "body_ratio": body_ratio,
            "body_threshold": threshold,
            "body_size": body,
            "range": rng,
            "delta": delta,
        }
        if rng == 0:
            return None, "zero_range", diagnostics

        if body < rng * threshold:
            return None, "body_too_small", diagnostics

        disp = "up" if c.close > c.open else "down"

        if delta is not None:
            if disp == "up" and delta <= 0:
                return None, "delta_not_confirming_up", diagnostics
            if disp == "down" and delta >= 0:
                return None, "delta_not_confirming_down", diagnostics

        return disp, "{direction}_conditions_passed".format(direction=disp), diagnostics

    def _displacement(self, c, delta):
        disp, _reason, _diagnostics = self._displacement_with_reason(c, delta)
        return disp

    # ============================================================
    #   SWEEP REAL
    # ============================================================
    def _sweep(self, c, prev):
        if not prev:
            return None

        if c.high > prev.high and c.close < prev.high:
            return "up"
        if c.low < prev.low and c.close > prev.low:
            return "down"
        return None

    # ============================================================
    #   MOMENTUM PRO (delta acelerado)
    # ============================================================
    def _momentum(self, c, prev, disp, delta, prev_delta):
        if not prev or not disp:
            return None

        rng = c.high - c.low
        if rng == 0:
            return None

        body = abs(c.close - c.open)
        if body < rng * 0.60:
            return None

        if disp == "up" and c.close <= prev.close:
            return None
        if disp == "down" and c.close >= prev.close:
            return None

        if delta is not None and prev_delta is not None:
            if disp == "up" and delta <= prev_delta:
                return None
            if disp == "down" and delta >= prev_delta:
                return None

        return disp

    # ============================================================
    #   INDUCEMENT PRO
    # ============================================================
    def _inducement(self, c, prev, disp, liquidity, premium, discount, delta):
        if not prev or not disp:
            return None

        eqh = liquidity.get("eqh")
        eql = liquidity.get("eql")

        if (
            disp == "down" and
            c.high > prev.high and
            c.body < c.range * 0.40 and
            discount and
            not eqh and
            delta is not None and delta < 0
        ):
            return "up"

        if (
            disp == "up" and
            c.low < prev.low and
            c.body < c.range * 0.40 and
            premium and
            not eql and
            delta is not None and delta > 0
        ):
            return "down"

        return None

    # ============================================================
    #   MITIGACIÓN LIGHT
    # ============================================================
    @staticmethod
    def _mitigation_overlap_reason(prev_close_inside_current_range, current_close_inside_prev_range):
        if prev_close_inside_current_range and current_close_inside_prev_range:
            return "both_close_overlaps"
        if prev_close_inside_current_range:
            return "previous_close_inside_current_range"
        if current_close_inside_prev_range:
            return "current_close_inside_previous_range"
        return "no_close_overlap"

    @staticmethod
    def _mitigation_light_snapshot(
        c,
        prev,
        *,
        value,
        reason,
        prev_close_inside_current_range,
        current_close_inside_prev_range,
    ):
        return {
            "value": value,
            "reason": reason,
            "prev_close_inside_current_range": prev_close_inside_current_range,
            "current_close_inside_prev_range": current_close_inside_prev_range,
            "current_low": c.low,
            "current_high": c.high,
            "current_close": c.close,
            "previous_low": None if prev is None else prev.low,
            "previous_high": None if prev is None else prev.high,
            "previous_close": None if prev is None else prev.close,
        }

    def _mitigation_light_diagnostics(self, c, prev):
        if not prev:
            return self._mitigation_light_snapshot(
                c,
                prev,
                value=False,
                reason="no_previous_candle",
                prev_close_inside_current_range=False,
                current_close_inside_prev_range=False,
            )

        prev_close_inside_current_range = c.low < prev.close < c.high
        current_close_inside_prev_range = prev.low < c.close < prev.high
        reason = self._mitigation_overlap_reason(
            prev_close_inside_current_range,
            current_close_inside_prev_range,
        )

        return self._mitigation_light_snapshot(
            c,
            prev,
            value=prev_close_inside_current_range or current_close_inside_prev_range,
            reason=reason,
            prev_close_inside_current_range=prev_close_inside_current_range,
            current_close_inside_prev_range=current_close_inside_prev_range,
        )

    def _mitigation_light(self, c, prev):
        return self._mitigation_light_diagnostics(c, prev)["value"]

    @staticmethod
    def _mitigation_direction(disp, momentum):
        return disp if disp in ("up", "down") else momentum

    @staticmethod
    def _mitigation_v2_payload(mitigation_overlap, mitigation_overlap_reason, contamination, reason):
        return {
            "mitigation_overlap": mitigation_overlap,
            "mitigation_overlap_reason": mitigation_overlap_reason,
            "mitigation_contamination": contamination,
            "mitigation_contamination_reason": reason,
            "mitigation_light_v2": contamination,
            "mitigation_light_v2_reason": reason,
        }

    @staticmethod
    def _mitigation_v2_counter_reasons(direction, sweep, absorption, breaker, fake_displacement, delta):
        counter_reasons = []

        if (direction == "up" and sweep == "up") or (direction == "down" and sweep == "down"):
            counter_reasons.append("counter_sweep")

        if (direction == "up" and absorption == "buy") or (direction == "down" and absorption == "sell"):
            counter_reasons.append("counter_absorption")

        if isinstance(breaker, dict):
            breaker_type = breaker.get("type")
            if (direction == "up" and breaker_type == "bearish") or (direction == "down" and breaker_type == "bullish"):
                counter_reasons.append("counter_breaker")

        if fake_displacement:
            counter_reasons.append("fake_displacement_true")

        if delta is not None:
            if (direction == "up" and delta <= 0) or (direction == "down" and delta >= 0):
                counter_reasons.append("delta_conflict")

        return counter_reasons

    @staticmethod
    def _mitigation_v2_reason_without_counter_reasons(mitigation_overlap_reason):
        if mitigation_overlap_reason in (
            "previous_close_inside_current_range",
            "current_close_inside_previous_range",
            "both_close_overlaps",
        ):
            return "overlap_only"
        return "insufficient_structural_context"

    def _mitigation_light_v2_shadow(
        self,
        mitigation_overlap,
        mitigation_overlap_reason,
        disp,
        momentum,
        sweep,
        absorption,
        breaker,
        fake_displacement,
        delta,
    ):
        direction = self._mitigation_direction(disp, momentum)
        if direction not in ("up", "down"):
            return self._mitigation_v2_payload(
                mitigation_overlap,
                mitigation_overlap_reason,
                False,
                "no_directional_context",
            )

        if not mitigation_overlap:
            return self._mitigation_v2_payload(
                False,
                mitigation_overlap_reason,
                False,
                "no_overlap",
            )

        counter_reasons = self._mitigation_v2_counter_reasons(
            direction,
            sweep,
            absorption,
            breaker,
            fake_displacement,
            delta,
        )
        if not counter_reasons:
            return self._mitigation_v2_payload(
                True,
                mitigation_overlap_reason,
                False,
                self._mitigation_v2_reason_without_counter_reasons(mitigation_overlap_reason),
            )

        return self._mitigation_v2_payload(
            True,
            mitigation_overlap_reason,
            True,
            "+".join(counter_reasons),
        )

    # ============================================================
    #   FAKE DISPLACEMENT PRO
    # ============================================================
    def _fake_displacement(self, c, prev, disp, sweep, inducement, breaker, absorption, liquidity, delta):
        if not disp:
            return False

        rng = c.high - c.low
        if rng == 0:
            return True

        if sweep or inducement or breaker or absorption:
            return False

        if delta is not None:
            if disp == "up" and delta <= 0:
                return True
            if disp == "down" and delta >= 0:
                return True

        wick_up   = c.high - max(c.open, c.close)
        wick_down = min(c.open, c.close) - c.low

        if disp == "up" and wick_down > rng * 0.45:
            return True
        if disp == "down" and wick_up > rng * 0.45:
            return True

        eqh = liquidity.get("eqh")
        eql = liquidity.get("eql")

        if disp == "up" and eqh:
            return True
        if disp == "down" and eql:
            return True

        return False

    # ============================================================
    #   ABSORCIÓN PRO
    # ============================================================
    def _absorption(self, c, prev, delta):
        if not prev:
            return None

        if c.high > prev.high and c.close < c.high:
            if delta is not None and delta < 0:
                return "buy"

        if c.low < prev.low and c.close > c.low:
            if delta is not None and delta > 0:
                return "sell"

        return None

    # ============================================================
    #   BREAKER PRO
    # ============================================================
    def _breaker(self, c, prev, sweep, delta, prev_delta):
        if not prev or not sweep:
            return None

        if delta is None or prev_delta is None:
            return None

        shift = delta - prev_delta

        if sweep == "down" and c.close > prev.close and shift > 0:
            return {"type": "bullish", "level": prev.low}

        if sweep == "up" and c.close < prev.close and shift < 0:
            return {"type": "bearish", "level": prev.high}

        return None

    # ============================================================
    #   LIQUIDEZ (EQH/EQL)
    # ============================================================
    def _liquidity(self, c, prev):
        if not prev:
            return {"eqh": False, "eql": False}

        eqh = abs(c.high - prev.high) <= 0.25
        eql = abs(c.low - prev.low) <= 0.25

        return {"eqh": eqh, "eql": eql}

    # ============================================================
    #   FVG
    # ============================================================
    def _fvg(self, c, prev, prev2):
        if not prev or not prev2:
            return None

        if prev2.high < prev.low and prev.low < c.low:
            return {"type": "bullish", "high": prev.low, "low": prev2.high}

        if prev2.low > prev.high and prev.high > c.high:
            return {"type": "bearish", "high": prev2.low, "low": prev.high}

        return None

    # ============================================================
    #   PREMIUM / DISCOUNT
    # ============================================================
    def _premium_discount(self, c):
        mid = (c.high + c.low) / 2
        return {
            "premium": c.close > mid,
            "discount": c.close < mid
        }

    # ============================================================
    #   SWINGS
    # ============================================================
    def _swings(self, c, prev):
        if not prev:
            return {"swing_high": False, "swing_low": False}

        return {
            "swing_high": c.high > prev.high,
            "swing_low": c.low < prev.low
        }

    # ============================================================
    #   COMPRESIÓN / EXPANSIÓN
    # ============================================================
    def _compression_expansion(self, c, prev):
        if not prev:
            return {"compression": False, "expansion": False}

        rng = c.high - c.low
        prev_rng = prev.high - prev.low

        if prev_rng == 0:
            return {"compression": False, "expansion": False}

        return {
            "compression": rng < prev_rng * 0.6,
            "expansion": rng > prev_rng * 1.5
        }

    # ============================================================
    #   API PRINCIPAL
    # ============================================================
    def process(self, c, delta=None, prev_delta=None):
        prev = self.prev
        prev2 = self.prev2

        disp, displacement_reason, displacement_diagnostics = self._displacement_with_reason(c, delta)
        sweep = self._sweep(c, prev)
        liquidity = self._liquidity(c, prev)
        premium_discount = self._premium_discount(c)

        inducement = self._inducement(
            c, prev, disp, liquidity,
            premium_discount["premium"],
            premium_discount["discount"],
            delta
        )

        absorption = self._absorption(c, prev, delta)
        breaker = self._breaker(c, prev, sweep, delta, prev_delta)
        momentum = self._momentum(c, prev, disp, delta, prev_delta)

        fake_disp = self._fake_displacement(
            c, prev, disp, sweep, inducement, breaker, absorption, liquidity, delta
        )
        mitigation_light_diagnostics = self._mitigation_light_diagnostics(c, prev)
        mitigation_light_v2_shadow = self._mitigation_light_v2_shadow(
            mitigation_light_diagnostics["value"],
            mitigation_light_diagnostics["reason"],
            disp,
            momentum,
            sweep,
            absorption,
            breaker,
            fake_disp,
            delta,
        )

        data = {
            "displacement": disp,
            "displacement_reason": displacement_reason,
            "displacement_body_ratio": displacement_diagnostics["body_ratio"],
            "displacement_body_threshold": displacement_diagnostics["body_threshold"],
            "displacement_body_size": displacement_diagnostics["body_size"],
            "displacement_range": displacement_diagnostics["range"],
            "displacement_delta": displacement_diagnostics["delta"],
            "sweep": sweep,
            "momentum": momentum,
            "inducement": inducement,
            "mitigation_light": mitigation_light_diagnostics["value"],
            "mitigation_light_reason": mitigation_light_diagnostics["reason"],
            "mitigation_light_prev_close_inside_current_range": mitigation_light_diagnostics["prev_close_inside_current_range"],
            "mitigation_light_current_close_inside_prev_range": mitigation_light_diagnostics["current_close_inside_prev_range"],
            "mitigation_light_current_low": mitigation_light_diagnostics["current_low"],
            "mitigation_light_current_high": mitigation_light_diagnostics["current_high"],
            "mitigation_light_current_close": mitigation_light_diagnostics["current_close"],
            "mitigation_light_previous_low": mitigation_light_diagnostics["previous_low"],
            "mitigation_light_previous_high": mitigation_light_diagnostics["previous_high"],
            "mitigation_light_previous_close": mitigation_light_diagnostics["previous_close"],
            "mitigation_overlap": mitigation_light_v2_shadow["mitigation_overlap"],
            "mitigation_overlap_reason": mitigation_light_v2_shadow["mitigation_overlap_reason"],
            "mitigation_contamination": mitigation_light_v2_shadow["mitigation_contamination"],
            "mitigation_contamination_reason": mitigation_light_v2_shadow["mitigation_contamination_reason"],
            "mitigation_light_v2": mitigation_light_v2_shadow["mitigation_light_v2"],
            "mitigation_light_v2_reason": mitigation_light_v2_shadow["mitigation_light_v2_reason"],
            "fake_displacement": fake_disp,
            "absorption": absorption,
            "breaker": breaker,
            "liquidity": liquidity,
            "fvg": self._fvg(c, prev, prev2),
            "premium": premium_discount["premium"],
            "discount": premium_discount["discount"],
            **self._swings(c, prev),
            **self._compression_expansion(c, prev),
            "ob": None  # OBEngine PRO lo llenará
        }

        self.prev2 = self.prev
        self.prev = c

        _decision_log(
            "process",
            True,
            "ok",
            "displacement={displacement} displacement_reason={displacement_reason} displacement_body_ratio={displacement_body_ratio} displacement_body_threshold={displacement_body_threshold} displacement_body_size={displacement_body_size} displacement_range={displacement_range} displacement_delta={displacement_delta} momentum={momentum} mitigation_light={mitigation_light} mitigation_light_reason={mitigation_light_reason} mitigation_light_prev_close_inside_current_range={mitigation_light_prev_close_inside_current_range} mitigation_light_current_close_inside_prev_range={mitigation_light_current_close_inside_prev_range} mitigation_light_current_low={mitigation_light_current_low} mitigation_light_current_high={mitigation_light_current_high} mitigation_light_current_close={mitigation_light_current_close} mitigation_light_previous_low={mitigation_light_previous_low} mitigation_light_previous_high={mitigation_light_previous_high} mitigation_light_previous_close={mitigation_light_previous_close} mitigation_overlap={mitigation_overlap} mitigation_overlap_reason={mitigation_overlap_reason} mitigation_contamination={mitigation_contamination} mitigation_contamination_reason={mitigation_contamination_reason} mitigation_light_v2={mitigation_light_v2} mitigation_light_v2_reason={mitigation_light_v2_reason} fake_displacement={fake_displacement}".format(
                displacement=data.get("displacement"),
                displacement_reason=data.get("displacement_reason"),
                displacement_body_ratio=data.get("displacement_body_ratio"),
                displacement_body_threshold=data.get("displacement_body_threshold"),
                displacement_body_size=data.get("displacement_body_size"),
                displacement_range=data.get("displacement_range"),
                displacement_delta=data.get("displacement_delta"),
                momentum=data.get("momentum"),
                mitigation_light=data.get("mitigation_light"),
                mitigation_light_reason=data.get("mitigation_light_reason"),
                mitigation_light_prev_close_inside_current_range=data.get("mitigation_light_prev_close_inside_current_range"),
                mitigation_light_current_close_inside_prev_range=data.get("mitigation_light_current_close_inside_prev_range"),
                mitigation_light_current_low=data.get("mitigation_light_current_low"),
                mitigation_light_current_high=data.get("mitigation_light_current_high"),
                mitigation_light_current_close=data.get("mitigation_light_current_close"),
                mitigation_light_previous_low=data.get("mitigation_light_previous_low"),
                mitigation_light_previous_high=data.get("mitigation_light_previous_high"),
                mitigation_light_previous_close=data.get("mitigation_light_previous_close"),
                mitigation_overlap=data.get("mitigation_overlap"),
                mitigation_overlap_reason=data.get("mitigation_overlap_reason"),
                mitigation_contamination=data.get("mitigation_contamination"),
                mitigation_contamination_reason=data.get("mitigation_contamination_reason"),
                mitigation_light_v2=data.get("mitigation_light_v2"),
                mitigation_light_v2_reason=data.get("mitigation_light_v2_reason"),
                fake_displacement=data.get("fake_displacement"),
            ),
        )

        return data
