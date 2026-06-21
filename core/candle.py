# core/candle.py

class Candle:
    """
    Candle PRO — Institucional + Delta PRO + Orderflow
    -------------------------------------------------
    - OHLCV completo
    - Orderflow real (bid/ask)
    - Delta PRO (delta, prev_delta, cumdelta)
    - Campos derivados seguros
    - No repaint de timestamp
    - Compatible con todo el pipeline institucional
    """

    def __init__(self, raw):
        # ============================
        #   DATOS BÁSICOS
        # ============================
        self.open       = raw.get("open")
        self.high       = raw.get("high")
        self.low        = raw.get("low")
        self.close      = raw.get("close")
        self.volume     = raw.get("volume", 0)
        self.timestamp  = raw.get("timestamp")  # NO se modifica nunca
        self.instrument = raw.get("instrument")
        self.barType    = raw.get("barType")
        self.barSize    = raw.get("barSize")
        self.isClosed   = raw.get("isClosed", True)

        # ============================
        #   ORDERFLOW REAL
        # ============================
        self.bid_volume = raw.get("bid_volume", None)
        self.ask_volume = raw.get("ask_volume", None)

        # ============================
        #   DELTA PRO (rellenado por Feed/Backend)
        # ============================
        self.delta      = 0.0
        self.prev_delta = 0.0
        self.cumdelta   = 0.0

        # ============================
        #   CAMPOS DERIVADOS
        # ============================
        self._recalc()

        # ============================
        #   CAMPOS HTF (placeholder)
        # ============================
        self.structure = None
        self.zones     = None
        self.intent    = None

    # ============================================================
    #   RECALCULAR CAMPOS DERIVADOS (SEGURO)
    # ============================================================
    def _recalc(self):
        o = self.open  if self.open  is not None else 0
        h = self.high  if self.high  is not None else o
        l = self.low   if self.low   is not None else o
        c = self.close if self.close is not None else o

        self.body       = abs(c - o)
        self.wick_up    = h - max(c, o)
        self.wick_down  = min(c, o) - l
        self.range      = h - l

    # ============================================================
    #   ACTUALIZAR VELA ABIERTA (INSTITUCIONAL)
    # ============================================================
    def update(self, raw):
        """
        Actualiza SOLO velas abiertas.
        No permite repaint de timestamp ni de velas cerradas.
        """

        if self.isClosed:
            return  # ❌ NO se actualiza una vela cerrada

        # OHLC
        self.open  = raw.get("open", self.open)
        self.high  = max(self.high, raw.get("high", self.high))
        self.low   = min(self.low,  raw.get("low",  self.low))
        self.close = raw.get("close", self.close)

        # volumen
        self.volume = raw.get("volume", self.volume)

        # orderflow real
        if "bid_volume" in raw:
            self.bid_volume = raw["bid_volume"]
        if "ask_volume" in raw:
            self.ask_volume = raw["ask_volume"]

        # estado
        self.isClosed = raw.get("isClosed", self.isClosed)

        # ❌ NO PERMITIR CAMBIAR TIMESTAMP
        # self.timestamp = raw.get("timestamp", self.timestamp)

        # recalcular derivados
        self._recalc()
