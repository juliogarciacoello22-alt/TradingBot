class MomentumDetector:

    def detect(self, candles, micro):
        """
        MOMENTUM INSTITUCIONAL — BIUMOLO INSTITUTIONAL
        Requisitos:
        - displacement real (no fake)
        - cuerpo dominante
        - rango expansivo
        - dirección alineada
        - wick contrario mínimo
        - continuidad institucional (displacement previo)
        - sweep previo
        - breaker / absorción / liquidez a favor
        """

        if len(candles) < 5:
            return None

        disp = micro.get("displacement")
        if disp not in ("up", "down"):
            return None

        # fake displacement → momentum inválido
        if micro.get("fake_displacement"):
            return None

        # sweep previo obligatorio
        if not micro.get("sweep"):
            return None

        c = candles[-1]   # vela actual
        p = candles[-2]   # vela previa
        p2 = candles[-3]  # vela previa-2 (para continuidad)

        breaker    = micro.get("breaker")
        absorption = micro.get("absorption")
        liquidity  = micro.get("liquidity", {}) or {}

        # ============================================================
        # 1. CUERPO DOMINANTE
        # ============================================================
        rango = c.high - c.low
        if rango <= 0:
            return None

        cuerpo = abs(c.close - c.open)
        if cuerpo < rango * 0.60:
            return None

        # ============================================================
        # 2. RANGO EXPANSIVO REAL
        # ============================================================
        last_ranges = [(x.high - x.low) for x in candles[-5:]]
        avg_range = sum(last_ranges) / len(last_ranges)

        if rango < avg_range * 1.15:
            return None

        # ============================================================
        # 3. DIRECCIÓN ALINEADA
        # ============================================================
        if disp == "up" and c.close <= c.open:
            return None

        if disp == "down" and c.close >= c.open:
            return None

        # ============================================================
        # 4. WICK CONTRARIO MUY PEQUEÑO
        # ============================================================
        wick_up   = c.high - max(c.open, c.close)
        wick_down = min(c.open, c.close) - c.low

        if disp == "up" and wick_down > rango * 0.08:
            return None

        if disp == "down" and wick_up > rango * 0.08:
            return None

        # ============================================================
        # 5. CONTINUIDAD INSTITUCIONAL REAL (CORREGIDO)
        # ============================================================
        # Regla institucional:
        # - vela previa NO debe ser fuerte en contra
        # - pero sí puede ser débil en contra
        prev_body = abs(p.close - p.open)
        prev_range = p.high - p.low

        if prev_range > 0 and prev_body > prev_range * 0.55:
            # vela previa fuerte en contra → momentum inválido
            if disp == "up" and p.close < p.open:
                return None
            if disp == "down" and p.close > p.open:
                return None

        # displacement previo (continuidad)
        disp_prev = "up" if p2.close > p2.open else "down"
        if disp_prev != disp:
            return None

        # ============================================================
        # 6. VALIDACIONES INSTITUCIONALES ADICIONALES
        # ============================================================
        breaker_bull = breaker and breaker.get("type") == "bullish"
        breaker_bear = breaker and breaker.get("type") == "bearish"

        absorption_buy  = absorption == "buy"
        absorption_sell = absorption == "sell"

        eqh = liquidity.get("eqh")
        eql = liquidity.get("eql")

        # ============================================================
        # 7. MOMENTUM ALCISTA
        # ============================================================
        if disp == "up":
            if breaker_bull or absorption_buy or eql:
                return "up"

        # ============================================================
        # 8. MOMENTUM BAJISTA
        # ============================================================
        if disp == "down":
            if breaker_bear or absorption_sell or eqh:
                return "down"

        return None
