class MitigationLightDetector:
    """
    MITIGACIÓN LIGERA — BIUMOLO INSTITUTIONAL
    Requisitos:
    - inducement → sweep → displacement real
    - NO fake displacement
    - toque rápido al OB/FVG micro
    - rechazo institucional (wick dominante)
    - OB/FVG NO mitigado
    - dirección institucional correcta
    - validación con breaker / momentum / absorción / liquidez
    """

    def detect(self, candles, micro):
        if not candles:
            return False

        candle = candles[-1]
        prev   = candles[-2] if len(candles) >= 2 else None

        inducement = micro.get("inducement")
        sweep      = micro.get("sweep")
        disp       = micro.get("displacement")
        momentum   = micro.get("momentum")
        absorption = micro.get("absorption")
        breaker    = micro.get("breaker")
        liquidity  = micro.get("liquidity", {}) or {}

        ob  = micro.get("ob")  if isinstance(micro.get("ob"), dict)  else None
        fvg = micro.get("fvg") if isinstance(micro.get("fvg"), dict) else None

        # ============================================================
        # 1. Requisitos institucionales mínimos
        # ============================================================
        if not inducement or not sweep or not disp:
            return False

        # fake displacement → NO mitigación
        if micro.get("fake_displacement"):
            return False

        # ============================================================
        # 2. Rechazo institucional (wick dominante)
        # ============================================================
        rango = candle.high - candle.low
        if rango <= 0:
            return False

        wick_up   = candle.high - max(candle.open, candle.close)
        wick_down = min(candle.open, candle.close) - candle.low

        rechazo = (
            wick_up > rango * 0.25 or
            wick_down > rango * 0.25
        )

        if not rechazo:
            return False

        # ============================================================
        # 3. Dirección institucional
        # ============================================================
        is_buy  = disp == "up"
        is_sell = disp == "down"

        # ============================================================
        # 4. Validación institucional adicional
        # ============================================================
        breaker_bull = breaker and breaker.get("type") == "bullish"
        breaker_bear = breaker and breaker.get("type") == "bearish"

        absorption_buy  = absorption == "buy"
        absorption_sell = absorption == "sell"

        momentum_up   = momentum == "up"
        momentum_down = momentum == "down"

        eqh = liquidity.get("eqh")
        eql = liquidity.get("eql")

        # ============================================================
        # 5. MITIGACIÓN EN OB MICRO
        # ============================================================
        if ob and not ob.get("mitigated", False):

            touched = (
                ob["low"] <= candle.low <= ob["high"] or
                ob["low"] <= candle.high <= ob["high"]
            )

            if touched:

                # BUY → mitigación en OB bajista
                if is_buy and ob.get("type") == "bearish":
                    if breaker_bull or absorption_buy or momentum_up or eql:
                        return True

                # SELL → mitigación en OB alcista
                if is_sell and ob.get("type") == "bullish":
                    if breaker_bear or absorption_sell or momentum_down or eqh:
                        return True

        # ============================================================
        # 6. MITIGACIÓN EN FVG MICRO
        # ============================================================
        if fvg and not fvg.get("mitigated", False):

            touched = (
                fvg["low"] <= candle.low <= fvg["high"] or
                fvg["low"] <= candle.high <= fvg["high"]
            )

            if touched:

                # BUY → mitigación en FVG bajista
                if is_buy and fvg.get("type") == "bearish":
                    if breaker_bull or absorption_buy or momentum_up or eql:
                        return True

                # SELL → mitigación en FVG alcista
                if is_sell and fvg.get("type") == "bullish":
                    if breaker_bear or absorption_sell or momentum_down or eqh:
                        return True

        return False
