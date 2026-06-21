class AbsorptionDetector:
    """
    Absorción Institucional — BIUMOLO INSTITUTIONAL
    ------------------------------------------------
    Detecta absorción REAL basada en:

    1. Wick contrario largo
    2. Cuerpo fuerte en dirección contraria
    3. Toque institucional en OB
    4. Continuidad institucional
    5. Validación con momentum / BOS / liquidez
    """

    def detect(self, candles, micro):
        if len(candles) < 3:
            return None

        c = candles[-1]   # vela actual
        p = candles[-2]   # vela previa

        disp       = micro.get("displacement")
        momentum   = micro.get("momentum")
        bos        = micro.get("bos")
        liquidity  = micro.get("liquidity", {}) or {}
        ob         = micro.get("ob") if isinstance(micro.get("ob"), dict) else None

        # ============================================================
        # 1. WICK CONTRARIO LARGO (institucional)
        # ============================================================
        rango = c.high - c.low
        if rango <= 0:
            return None

        wick_up   = c.high - max(c.open, c.close)
        wick_down = min(c.open, c.close) - c.low

        wick_ratio = 0.40  # institucional estricto

        wick_up_ok   = wick_up   >= rango * wick_ratio
        wick_down_ok = wick_down >= rango * wick_ratio

        # ============================================================
        # 2. CUERPO EN DIRECCIÓN CONTRARIA
        # ============================================================
        cuerpo = abs(c.close - c.open)
        if cuerpo < rango * 0.30:
            return None

        # ============================================================
        # 3. TOQUE INSTITUCIONAL EN OB (wick, no cuerpo)
        # ============================================================
        touched_zone = False

        if ob:
            if ob["low"] <= c.high <= ob["high"] or ob["low"] <= c.low <= ob["high"]:
                touched_zone = True

        if not touched_zone:
            return None

        # ============================================================
        # 4. CONTINUIDAD INSTITUCIONAL (cierre contra el previo)
        # ============================================================
        mid_prev = (p.open + p.close) / 2

        # ============================================================
        # 5. VALIDACIONES INSTITUCIONALES ADICIONALES
        # ============================================================

        # momentum a favor de la absorción
        momentum_up_ok   = momentum == "up"
        momentum_down_ok = momentum == "down"

        # BOS institucional
        bos_up_ok   = bos == "up"
        bos_down_ok = bos == "down"

        # liquidez institucional
        eqh = liquidity.get("eqh")
        eql = liquidity.get("eql")

        # ============================================================
        # 6. ABSORCIÓN BAJISTA (instituciones vendiendo)
        # ============================================================
        if disp == "up" and wick_up_ok:
            if c.close < mid_prev:

                # validaciones institucionales
                if momentum_down_ok or bos_down_ok or eqh:
                    return "sell"

        # ============================================================
        # 7. ABSORCIÓN ALCISTA (instituciones comprando)
        # ============================================================
        if disp == "down" and wick_down_ok:
            if c.close > mid_prev:

                # validaciones institucionales
                if momentum_up_ok or bos_up_ok or eql:
                    return "buy"

        return None
