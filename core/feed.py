# core/feed.py
from core.candle import Candle
from core.delta import delta_calc


class Feed:
    """
    Feed PRO — Institucional + Delta PRO + Orderflow
    ------------------------------------------------
    - Acepta SOLO velas 1m cerradas
    - No repaint
    - No sobrescribe timestamp
    - High/Low correctos
    - Delta real o proxy
    - prev_delta correcto
    - cumdelta incremental sin retraso
    - Buffer seguro
    """

    def __init__(self):
        self.data = {"1m": []}

    # ============================================================
    #   NORMALIZAR BARSIZE
    # ============================================================
    def normalize_bar_size(self, barSize):
        if isinstance(barSize, int):
            return barSize

        if isinstance(barSize, str):
            barSize = barSize.lower().strip()

            if barSize.isdigit():
                return int(barSize)

            if barSize.endswith("m"):
                num = barSize.replace("m", "")
                if num.isdigit():
                    return int(num)

            if "minute" in barSize:
                num = barSize.replace("minute", "").strip()
                if num.isdigit():
                    return int(num)

        return None

    # ============================================================
    #   PUSH — SIN REPAINT + DELTA PRO
    # ============================================================
    def push(self, raw):

        # Si no viene barSize → asumir 1m cerrada
        if raw.get("barSize") is None:
            raw["barType"] = "Minute"
            raw["barSize"] = 1
            raw["isClosed"] = True

        candle = Candle(raw)
        barSize = self.normalize_bar_size(candle.barSize)

        # SOLO aceptamos 1m
        if barSize != 1:
            return False

        tf = "1m"
        buffer = self.data[tf]

        # ============================================================
        #   CASO 1 — PRIMERA VELA
        # ============================================================
        if not buffer:
            if candle.isClosed:

                candle.delta = delta_calc.compute_delta(candle)
                candle.prev_delta = 0.0
                candle.cumdelta = candle.delta

                buffer.append(candle)
                return True

            return False

        last = buffer[-1]

        # ============================================================
        #   CASO 2 — MISMO TIMESTAMP (vela abierta)
        # ============================================================
        if candle.timestamp == last.timestamp:

            if last.isClosed:
                return False  # no repaint permitido

            # actualizar OHLC
            last.high = max(last.high, candle.high)
            last.low  = min(last.low,  candle.low)
            last.close = candle.close
            last.volume += candle.volume
            last.isClosed = candle.isClosed

            # delta en vela abierta
            last.delta = delta_calc.compute_delta(last)

            # cumdelta NO se actualiza en vela abierta
            last.cumdelta = last.cumdelta  # mantener valor previo

            return True

        # ============================================================
        #   CASO 3 — NUEVA VELA (cerrada)
        # ============================================================
        if candle.timestamp > last.timestamp:

            if not candle.isClosed:
                return False

            # delta actual
            candle.delta = delta_calc.compute_delta(candle)

            # prev_delta = delta de la vela anterior
            candle.prev_delta = last.delta if last.delta is not None else 0.0

            # cumdelta incremental
            candle.cumdelta = (last.cumdelta or 0.0) + candle.delta

            buffer.append(candle)

            # buffer seguro
            if len(buffer) > 5000:
                self.data["1m"] = buffer[-2000:]

            return True

        # ============================================================
        #   CASO 4 — TIMESTAMP ATRASADO
        # ============================================================
        return False

    # ============================================================
    #   GETTERS
    # ============================================================
    def get_candles(self, timeframe):
        return self.data.get(timeframe, [])

    def get_tf(self, timeframe):
        return self.data.get(timeframe, [])
