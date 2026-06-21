class StructureDetector:
    """
    StructureDetector Institucional
    -------------------------------
    - Usa swings institucionales
    - Usa BOS institucional
    - Detecta CHOCH real
    - Mantiene tendencia sin repaint
    """

    def __init__(self):
        self.last_swing_high = None
        self.last_swing_low  = None
        self.trend = "neutral"
        self.last_count = 0  # ← para detectar resets

    # ============================================================
    #   RESET AUTOMÁTICO (CRÍTICO)
    # ============================================================
    def _auto_reset(self, candles):
        if len(candles) < self.last_count:
            # TF fue reseteado → reset interno
            self.last_swing_high = None
            self.last_swing_low  = None
            self.trend = "neutral"
        self.last_count = len(candles)

    # ============================================================
    #   1. Swing High / Swing Low institucional
    # ============================================================
    def _is_swing_high(self, candles, i):
        if i < 2 or i > len(candles) - 3:
            return False

        c1 = candles[i-2]
        c2 = candles[i-1]
        c3 = candles[i]
        c4 = candles[i+1]
        c5 = candles[i+2]

        # Todos deben estar cerrados
        if not (c1.isClosed and c2.isClosed and c3.isClosed and c4.isClosed and c5.isClosed):
            return False

        # Rango mínimo institucional
        if c3.range == 0 or c3.body < c3.range * 0.25:
            return False

        return (
            c3.high > c1.high and
            c3.high > c2.high and
            c3.high > c4.high and
            c3.high > c5.high
        )

    def _is_swing_low(self, candles, i):
        if i < 2 or i > len(candles) - 3:
            return False

        c1 = candles[i-2]
        c2 = candles[i-1]
        c3 = candles[i]
        c4 = candles[i+1]
        c5 = candles[i+2]

        if not (c1.isClosed and c2.isClosed and c3.isClosed and c4.isClosed and c5.isClosed):
            return False

        if c3.range == 0 or c3.body < c3.range * 0.25:
            return False

        return (
            c3.low < c1.low and
            c3.low < c2.low and
            c3.low < c4.low and
            c3.low < c5.low
        )

    # ============================================================
    #   2. Detectar estructura institucional
    # ============================================================
    def detect(self, candles):
        bos = None
        choch = None

        # Reset automático si TF fue reiniciado
        self._auto_reset(candles)

        if len(candles) < 7:
            return {"bos": None, "choch": None, "trend": self.trend}

        for i in range(2, len(candles) - 2):

            c = candles[i]

            # --------------------------------------------------------
            #   SWING HIGH
            # --------------------------------------------------------
            if self._is_swing_high(candles, i):

                if self.last_swing_high is None:
                    self.last_swing_high = c.high

                # BOS bajista → close por debajo del swing low previo
                if self.last_swing_low and c.close < self.last_swing_low:
                    bos = "down"

                    if self.trend == "bullish":
                        choch = "down"

                    self.trend = "bearish"

                self.last_swing_high = c.high

            # --------------------------------------------------------
            #   SWING LOW
            # --------------------------------------------------------
            if self._is_swing_low(candles, i):

                if self.last_swing_low is None:
                    self.last_swing_low = c.low

                # BOS alcista → close por encima del swing high previo
                if self.last_swing_high and c.close > self.last_swing_high:
                    bos = "up"

                    if self.trend == "bearish":
                        choch = "up"

                    self.trend = "bullish"

                self.last_swing_low = c.low

        return {
            "bos": bos,
            "choch": choch,
            "trend": self.trend
        }
