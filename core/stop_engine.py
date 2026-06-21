class StopEngine:
    """
    Stop Engine Institucional
    -------------------------
    Gestión REAL institucional del stop:

    1. Break-even por mitigación del OB
    2. Break-even por BOS protegido
    3. Trailing por swing protegido
    4. Trailing por liquidez tomada
    """

    def __init__(self):
        pass

    # ============================================================
    #   1. BREAK-EVEN POR MITIGACIÓN DEL OB (REAL)
    # ============================================================
    def be_on_mitigation(self, price, ob, side):
        """
        Mitigación institucional:
        BUY  → precio toca el OPEN del OB alcista
        SELL → precio toca el OPEN del OB bajista
        """
        try:
            if not ob:
                return False

            ob_open = ob.get("open")
            if ob_open is None:
                return False

            if side == "BUY" and price <= ob_open:
                return True

            if side == "SELL" and price >= ob_open:
                return True

            return False

        except:
            return False

    # ============================================================
    #   2. BREAK-EVEN POR BOS PROTEGIDO
    # ============================================================
    def be_on_bos(self, micro, side, entry):
        """
        Si el BOS institucional se valida y el precio se aleja
        lo suficiente del entry, mover a break-even.
        """
        try:
            if not micro.get("bos_valid"):
                return False

            bos_price = micro.get("bos_price")
            if bos_price is None:
                return False

            if side == "BUY" and bos_price > entry:
                return True

            if side == "SELL" and bos_price < entry:
                return True

            return False

        except:
            return False

    # ============================================================
    #   3. TRAILING POR SWING PROTEGIDO
    # ============================================================
    def trailing_by_swing(self, micro, side):
        """
        BUY  → stop debajo del último swing_low protegido
        SELL → stop encima del último swing_high protegido
        """
        try:
            swing_high = micro.get("swing_high")
            swing_low  = micro.get("swing_low")

            if side == "BUY" and swing_low:
                return swing_low.get("price")

            if side == "SELL" and swing_high:
                return swing_high.get("price")

            return None

        except:
            return None

    # ============================================================
    #   4. TRAILING POR LIQUIDEZ TOMADA
    # ============================================================
    def trailing_by_liquidity(self, micro, side):
        """
        BUY  → si se toma EQH, subir stop al swing_low protegido
        SELL → si se toma EQL, bajar stop al swing_high protegido
        """
        try:
            liq = micro.get("liquidity", {})

            if side == "BUY" and liq.get("eqh"):
                sl = micro.get("swing_low")
                return sl.get("price") if sl else None

            if side == "SELL" and liq.get("eql"):
                sh = micro.get("swing_high")
                return sh.get("price") if sh else None

            return None

        except:
            return None

    # ============================================================
    #   5. EVALUACIÓN PRINCIPAL (CONTRATO INSTITUCIONAL)
    # ============================================================
    def evaluate(self, side, price, entry, stop, micro, ob):
        """
        Devuelve un nuevo stop institucional.
        """
        try:
            # 1. Break-even por mitigación del OB
            if self.be_on_mitigation(price, ob, side):
                return entry

            # 2. Break-even por BOS protegido
            if self.be_on_bos(micro, side, entry):
                return entry

            # 3. Trailing por swing protegido
            swing_trail = self.trailing_by_swing(micro, side)
            if swing_trail:
                return swing_trail

            # 4. Trailing por liquidez tomada
            liq_trail = self.trailing_by_liquidity(micro, side)
            if liq_trail:
                return liq_trail

            # Nada aplica → mantener stop original
            return stop

        except:
            return stop
