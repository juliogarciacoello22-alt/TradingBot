# core/swing_engine.py

class SwingEngine:
    """
    SwingEngine PRO — Institucional
    --------------------------------
    Detecta swing highs y swing lows REALES:
    - sin repaint
    - basados en velas cerradas
    - validación institucional estricta
    - persistentes
    - compatibles con Microestructura PRO
    """

    def __init__(self, lookback=5):
        self.lookback = lookback
        self.last_swing_high = None
        self.last_swing_low  = None
        self.last_count = 0  # para reset automático

    # ============================================================
    #   RESET AUTOMÁTICO (si el buffer se reduce)
    # ============================================================
    def _auto_reset(self, candles):
        if len(candles) < self.last_count:
            self.last_swing_high = None
            self.last_swing_low  = None
        self.last_count = len(candles)

    # ============================================================
    #   VALIDACIÓN INSTITUCIONAL DE LA VELA CENTRAL
    # ============================================================
    def _valid_center(self, c):
        if c.range == 0:
            return False

        # evitar dojis
        if c.body < c.range * 0.25:
            return False

        # evitar wicks dominantes
        if c.wick_up > c.range * 0.50:
            return False
        if c.wick_down > c.range * 0.50:
            return False

        return True

    # ============================================================
    #   DETECTAR SWINGS INSTITUCIONALES
    # ============================================================
    def detect_swings(self, candles):
        try:
            self._auto_reset(candles)

            n = len(candles)
            if n < self.lookback:
                return self.last_swing_high, self.last_swing_low

            # ventana institucional: c1 c2 c3 c4 c5
            c1 = candles[-5]
            c2 = candles[-4]
            c3 = candles[-3]   # centro
            c4 = candles[-2]
            c5 = candles[-1]

            # solo velas cerradas → sin repaint
            if not (c1.isClosed and c2.isClosed and c3.isClosed and c4.isClosed and c5.isClosed):
                return self.last_swing_high, self.last_swing_low

            # validar vela central institucional
            if not self._valid_center(c3):
                return self.last_swing_high, self.last_swing_low

            # ============================================================
            #   SWING HIGH INSTITUCIONAL
            # ============================================================
            if (
                c3.high > c2.high and
                c3.high > c4.high and
                c3.high > c1.high and
                c3.high > c5.high
            ):
                self.last_swing_high = {
                    "type": "high",
                    "price": c3.high,
                    "index": n - 3,
                }

            # ============================================================
            #   SWING LOW INSTITUCIONAL
            # ============================================================
            if (
                c3.low < c2.low and
                c3.low < c4.low and
                c3.low < c1.low and
                c3.low < c5.low
            ):
                self.last_swing_low = {
                    "type": "low",
                    "price": c3.low,
                    "index": n - 3,
                }

            return self.last_swing_high, self.last_swing_low

        except Exception as e:
            print("ERROR EN SWING ENGINE:", e)
            return self.last_swing_high, self.last_swing_low
