from core.candle import Candle

class TimeframeBuilder:
    """
    TimeframeBuilder Institucional
    ------------------------------
    - Construye velas HTF sin repaint
    - Mantiene high/low correctos
    - Timestamp = inicio del bucket
    - Cierra velas correctamente
    """

    def __init__(self, size):
        self.size = size              # tamaño en minutos (5, 30, 240)
        self.current = None           # vela HTF abierta
        self.series = []              # historial HTF (solo velas cerradas)

    # ============================================================
    #   RESET (CRÍTICO PARA GAPS)
    # ============================================================
    def reset(self):
        self.current = None
        self.series = []

    # ============================================================
    #   1. Alinear timestamp al inicio del bloque
    # ============================================================
    def _bucket(self, ts):
        return ts - (ts % (self.size * 60))

    # ============================================================
    #   2. Actualizar con vela 1m (sin repaint)
    # ============================================================
    def update(self, c1):
        ts = c1.timestamp
        bucket = self._bucket(ts)

        # ------------------------------------------------------------
        # Caso 1: No existe vela HTF abierta → crearla
        # ------------------------------------------------------------
        if self.current is None:
            self.current = Candle({
                "open": c1.open,
                "high": c1.high,
                "low": c1.low,
                "close": c1.close,
                "volume": c1.volume,
                "timestamp": bucket,
                "instrument": c1.instrument,
                "barType": "HTF",
                "barSize": self.size,
                "isClosed": False
            })
            return

        # ------------------------------------------------------------
        # Caso 2: La vela pertenece al mismo bucket → actualizar
        # ------------------------------------------------------------
        if self.current.timestamp == bucket:

            # Si ya está cerrada → NO REPAINT
            if self.current.isClosed:
                return

            self.current.high = max(self.current.high, c1.high)
            self.current.low  = min(self.current.low,  c1.low)
            self.current.close = c1.close
            self.current.volume += c1.volume

            return

        # ------------------------------------------------------------
        # Caso 3: Bucket nuevo → cerrar la vela anterior
        # ------------------------------------------------------------
        if bucket > self.current.timestamp:

            self.current.isClosed = True
            self.series.append(self.current)

            self.current = Candle({
                "open": c1.open,
                "high": c1.high,
                "low": c1.low,
                "close": c1.close,
                "volume": c1.volume,
                "timestamp": bucket,
                "instrument": c1.instrument,
                "barType": "HTF",
                "barSize": self.size,
                "isClosed": False
            })
            return

        # ------------------------------------------------------------
        # Caso 4: Timestamp atrasado → descartar
        # ------------------------------------------------------------
        if bucket < self.current.timestamp:
            return

    # ============================================================
    #   3. Obtener serie (cerradas + abierta)
    # ============================================================
    def get_series(self):
        if self.current:
            return self.series + [self.current]
        return self.series.copy()
