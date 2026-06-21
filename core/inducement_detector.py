class InducementDetector:
    """
    INDUCEMENT INSTITUCIONAL — BIUMOLO INSTITUTIONAL
    Detecta inducement real:
    - mini swing contra tendencia
    - NO toma liquidez mayor
    - ocurre justo antes del sweep/displacement real
    - validación con breaker / absorción / momentum
    - validación con premium/discount
    - validación con forecast (liquidez futura)
    """

    def detect(self, candles, micro, forecast=None):
        if len(candles) < 5:
            return False

        c1 = candles[-1]   # vela actual
        c2 = candles[-2]   # mini swing
        c3 = candles[-3]   # swing previo

        disp       = micro.get("displacement")
        sweep      = micro.get("sweep")
        momentum   = micro.get("momentum")
        absorption = micro.get("absorption")
        breaker    = micro.get("breaker")
        liquidity  = micro.get("liquidity", {}) or {}

        premium  = micro.get("premium")
        discount = micro.get("discount")

        eqh = liquidity.get("eqh")
        eql = liquidity.get("eql")

        # ============================================================
        # 1. Debe existir intención real (sweep o displacement)
        # ============================================================
        if not sweep and not disp:
            return False

        # fake displacement → NO inducement
        if micro.get("fake_displacement"):
            return False

        # ============================================================
        # 2. Mini swing contra tendencia (institucional)
        # ============================================================
        inducement_up = (
            c2.high > c3.high and
            c2.low  > c3.low  and
            disp == "down"
        )

        inducement_down = (
            c2.low  < c3.low  and
            c2.high < c3.high and
            disp == "up"
        )

        if not (inducement_up or inducement_down):
            return False

        # ============================================================
        # 3. Validación institucional del mini‑swing
        # ============================================================
        # mini swing debe ser pequeño → cuerpo NO dominante
        if c2.range == 0 or c2.body > c2.range * 0.40:
            return False

        # ============================================================
        # 4. No debe tomar liquidez mayor
        # ============================================================
        if eqh or eql:
            return False

        # ============================================================
        # 5. Validación premium/discount (CORREGIDO)
        # ============================================================
        # inducement UP → discount
        if inducement_up and not discount:
            return False

        # inducement DOWN → premium
        if inducement_down and not premium:
            return False

        # ============================================================
        # 6. Validación institucional adicional
        # ============================================================
        breaker_bull = breaker and breaker.get("type") == "bullish"
        breaker_bear = breaker and breaker.get("type") == "bearish"

        absorption_buy  = absorption == "buy"
        absorption_sell = absorption == "sell"

        momentum_up   = momentum == "up"
        momentum_down = momentum == "down"

        # ============================================================
        # 7. Validación con forecast (liquidez futura)
        # ============================================================
        if forecast:
            future_eqh = forecast.get("future_eqh")
            future_eql = forecast.get("future_eql")

            if inducement_up and not future_eql:
                return False

            if inducement_down and not future_eqh:
                return False

        # ============================================================
        # 8. Confirmación institucional final
        # ============================================================
        if inducement_up:
            if breaker_bear or absorption_sell or momentum_down:
                return True

        if inducement_down:
            if breaker_bull or absorption_buy or momentum_up:
                return True

        return False
