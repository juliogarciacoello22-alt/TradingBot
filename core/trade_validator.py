class TradeValidator:

    def __init__(self):
        pass

    # ============================================================
    #   1. NO OPERAR EN COMPRESIÓN
    # ============================================================
    def validate_compression(self, micro):
        return micro.get("compression") is False

    # ============================================================
    #   2. NO OPERAR CONTRA LIQUIDEZ
    # ============================================================
    def validate_liquidity(self, micro, direction):
        liq = micro.get("liquidity", {})

        # EQH es un objetivo favorable para LONG; EQL debajo es el riesgo.
        if direction == "long" and liq.get("eql"):
            return False

        # EQL es un objetivo favorable para SHORT; EQH encima es el riesgo.
        if direction == "short" and liq.get("eqh"):
            return False

        return True

    # ============================================================
    #   3. REQUIERE INTENCIÓN REAL
    # ============================================================
    def validate_intent(self, micro):
        return (
            micro.get("momentum") is not None or
            micro.get("displacement") is not None
        )

    # ============================================================
    #   4. NO OPERAR EN ABSORCIÓN CONTRARIA
    # ============================================================
    def validate_absorption(self, micro, direction):
        absorption = micro.get("absorption")

        if direction == "long" and absorption == "sell":
            return False

        if direction == "short" and absorption == "buy":
            return False

        return True

    # ============================================================
    #   5. VALIDACIÓN PRINCIPAL
    # ============================================================
    def validate(self, direction, micro):

        if direction is None:
            return False, "sin dirección"

        if not self.validate_compression(micro):
            return False, "compresión"

        if not self.validate_liquidity(micro, direction):
            return False, "liquidez en contra"

        if not self.validate_intent(micro):
            return False, "sin intención"

        if not self.validate_absorption(micro, direction):
            return False, "absorción contraria"

        return True, "OK"
