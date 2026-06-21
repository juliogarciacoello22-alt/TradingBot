class FakeDisplacementDetector:
    """
    FAKE DISPLACEMENT — BIUMOLO INSTITUTIONAL
    Detecta trampas institucionales reales:
    - displacement sin intención
    - cuerpo débil
    - wick contrario dominante
    - NO continuidad
    - NO OB/FVG a favor
    - rango pequeño o cierre débil
    - validación con liquidez / breaker / absorción
    """

    def detect(self, candles, micro):
        if len(candles) < 3:
            return None

        c = candles[-1]
        p = candles[-2]

        disp       = micro.get("displacement")
        momentum   = micro.get("momentum")
        sweep      = micro.get("sweep")
        inducement = micro.get("inducement")
        breaker    = micro.get("breaker")
        absorption = micro.get("absorption")
        liquidity  = micro.get("liquidity", {}) or {}

        ob  = micro.get("ob")  if isinstance(micro.get("ob"), dict)  else None
        fvg = micro.get("fvg") if isinstance(micro.get("fvg"), dict) else None

        rango  = c.high - c.low
        if rango <= 0:
            return "fake"

        cuerpo = abs(c.close - c.open)

        # ============================================================
        # 1. INTENCIÓN REAL → NO ES FAKE
        # ============================================================
        if momentum:
            return None
        if sweep:
            return None
        if inducement:
            return None

        # breaker a favor → NO fake
        if breaker:
            return None

        # absorción a favor → NO fake
        if absorption:
            return None

        # ============================================================
        # 2. OB/FVG EN CONTRA → FAKE (CORREGIDO)
        # ============================================================
        if ob:
            if disp == "up" and ob["type"] == "bearish":
                return "fake"
            if disp == "down" and ob["type"] == "bullish":
                return "fake"

        if fvg:
            if disp == "up" and fvg.get("direction") == "bearish":
                return "fake"
            if disp == "down" and fvg.get("direction") == "bullish":
                return "fake"

        # ============================================================
        # 3. CUERPO DÉBIL
        # ============================================================
        if cuerpo < rango * 0.25:
            return "fake"

        # ============================================================
        # 4. WICK CONTRARIO DOMINANTE
        # ============================================================
        wick_up   = c.high - max(c.open, c.close)
        wick_down = min(c.open, c.close) - c.low

        if disp == "up" and wick_down > rango * 0.45:
            return "fake"

        if disp == "down" and wick_up > rango * 0.45:
            return "fake"

        # ============================================================
        # 5. CIERRE DÉBIL (no hay continuidad)
        # ============================================================
        mid_prev = (p.open + p.close) / 2

        if disp == "up" and c.close < mid_prev:
            return "fake"

        if disp == "down" and c.close > mid_prev:
            return "fake"

        # ============================================================
        # 6. RANGO PEQUEÑO (fake retail)
        # ============================================================
        if rango < (abs(p.close - p.open) * 0.5):
            return "fake"

        # ============================================================
        # 7. LIQUIDEZ EN CONTRA → FAKE
        # ============================================================
        eqh = liquidity.get("eqh")
        eql = liquidity.get("eql")

        if disp == "up" and eqh:
            return "fake"

        if disp == "down" and eql:
            return "fake"

        # ============================================================
        # 8. FALTA DE CONTINUIDAD INSTITUCIONAL (CORREGIDO)
        # ============================================================
        disp_prev = "up" if p.close > p.open else "down"
        if disp_prev != disp:
            return "fake"

        return None
