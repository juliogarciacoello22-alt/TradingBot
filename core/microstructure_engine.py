# core/microstructure_engine.py

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
    def _displacement(self, c, delta):
        body = abs(c.close - c.open)
        rng = c.high - c.low
        if rng == 0:
            return None

        if body < rng * 0.55:
            return None

        disp = "up" if c.close > c.open else "down"

        if delta is not None:
            if disp == "up" and delta <= 0:
                return None
            if disp == "down" and delta >= 0:
                return None

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
    def _mitigation_light(self, c, prev):
        if not prev:
            return False
        return (
            (c.low < prev.close < c.high) or
            (prev.low < c.close < prev.high)
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

        disp = self._displacement(c, delta)
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

        data = {
            "displacement": disp,
            "sweep": sweep,
            "momentum": momentum,
            "inducement": inducement,
            "mitigation_light": self._mitigation_light(c, prev),
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

        return data
