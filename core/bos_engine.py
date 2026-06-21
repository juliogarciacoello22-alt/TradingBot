class BOSEngine:
    """
    BOS Engine Institucional
    ------------------------
    Detecta rupturas de estructura REALES basadas en:
    - swings confirmados
    - displacement institucional
    - continuidad direccional
    - no fake displacement
    - no absorción en contra
    """

    def __init__(self):
        self.last_broken_high = None
        self.last_broken_low  = None

    # ============================================================
    #   1. DISPLACEMENT INSTITUCIONAL
    # ============================================================
    def _valid_displacement(self, candle):
        if candle.range == 0:
            return False

        body_ratio = candle.body / candle.range

        # cuerpo > 55% del rango → institucional
        return body_ratio >= 0.55

    # ============================================================
    #   2. CONTINUIDAD INSTITUCIONAL
    # ============================================================
    def _continuity(self, candle, prev):
        if not prev:
            return False

        # vela direccional fuerte
        if candle.body <= prev.body:
            return False

        # cierre más allá del cierre previo
        if candle.close > prev.close and candle.open >= prev.close:
            return True

        if candle.close < prev.close and candle.open <= prev.close:
            return True

        return False

    # ============================================================
    #   3. BOS PRINCIPAL
    # ============================================================
    def detect_bos(self, candles, swing_high, swing_low):
        try:
            last = candles[-1]
            prev = candles[-2] if len(candles) > 1 else None

            if not prev:
                return {"bos": None, "valid": False}

            # ============================================================
            #   BOS ALCISTA
            # ============================================================
            if swing_high and "price" in swing_high:
                swing_price = swing_high["price"]

                # evitar romper el mismo swing dos veces
                if swing_price != self.last_broken_high:

                    # ruptura real → close por encima del swing
                    if last.close > swing_price:

                        # displacement institucional
                        if not self._valid_displacement(last):
                            return {"bos": None, "valid": False}

                        # continuidad institucional
                        if not self._continuity(last, prev):
                            return {"bos": None, "valid": False}

                        # registrar swing roto
                        self.last_broken_high = swing_price

                        displacement = abs(last.close - swing_price)

                        return {
                            "bos": "up",
                            "price": swing_price,
                            "displacement": displacement,
                            "valid": True
                        }

            # ============================================================
            #   BOS BAJISTA
            # ============================================================
            if swing_low and "price" in swing_low:
                swing_price = swing_low["price"]

                if swing_price != self.last_broken_low:

                    if last.close < swing_price:

                        if not self._valid_displacement(last):
                            return {"bos": None, "valid": False}

                        if not self._continuity(last, prev):
                            return {"bos": None, "valid": False}

                        self.last_broken_low = swing_price

                        displacement = abs(last.close - swing_price)

                        return {
                            "bos": "down",
                            "price": swing_price,
                            "displacement": displacement,
                            "valid": True
                        }

            # ============================================================
            #   SIN BOS
            # ============================================================
            return {"bos": None, "valid": False}

        except Exception as e:
            print("ERROR EN BOS ENGINE:", e)
            return {
                "bos": None,
                "price": None,
                "displacement": None,
                "valid": False,
                "error": str(e)
            }
