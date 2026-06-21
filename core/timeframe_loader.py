from core.timeframe_builder import TimeframeBuilder
from core.structure import StructureDetector
from core.biumolo_config import BASIC_LOG_ONLY


class TimeframeLoader:
    """
    TimeframeLoader PRO — Institucional
    -----------------------------------
    - Reconstruye 1m → 5m → 30m → 4h sin repaint
    - NO incluye velas abiertas en HTF
    - Reset automático en gaps
    - Buffers limpios
    - Estructura 4H institucional
    - Premium/Discount institucional
    """

    def __init__(self, api):
        self.api = api

        # Builders institucionales (sin repaint)
        self.builder_5m   = TimeframeBuilder(size=5)
        self.builder_30m  = TimeframeBuilder(size=30)
        self.builder_4h   = TimeframeBuilder(size=240)

        self.structure_detector = StructureDetector()

        # Contenedor de TF en la API
        if not hasattr(self.api, "timeframes"):
            self.api.timeframes = {}

        tf = self.api.timeframes
        for key in ("1m", "5m", "30m", "4h"):
            tf.setdefault(key, [])

        # Último timestamp procesado
        self.last_1m_ts = None

    # ============================================================
    #   CARGAR TIMEFRAMES (SIN REPAINT + HTF CERRADO)
    # ============================================================
    def load(self):
        tf = self.api.timeframes

        # ------------------------------------------------------------
        # 1. LEER SOLO LAS VELAS NUEVAS DEL FEED
        # ------------------------------------------------------------
        all_1m = self.api.feed.get_tf("1m")

        if not all_1m:
            return tf

        # Ordenar por timestamp
        all_1m = sorted(all_1m, key=lambda c: c.timestamp)

        for c in all_1m:

            # Saltar velas ya procesadas
            if self.last_1m_ts is not None and c.timestamp <= self.last_1m_ts:
                continue

            # GAP DETECTADO → reset de builders
            if self.last_1m_ts is not None:
                if c.timestamp - self.last_1m_ts > 120000:  # > 2 minutos
                    self.builder_5m.reset()
                    self.builder_30m.reset()
                    self.builder_4h.reset()

            # Registrar nueva vela 1m
            tf["1m"].append(c)
            self.last_1m_ts = c.timestamp

            # --------------------------------------------------------
            #   ACTUALIZAR BUILDERS SOLO CON VELAS CERRADAS
            # --------------------------------------------------------
            if c.isClosed:
                self.builder_5m.update(c)
                self.builder_30m.update(c)
                self.builder_4h.update(c)

        # ------------------------------------------------------------
        # 2. LEER SERIES CERRADAS DESDE LOS BUILDERS
        # ------------------------------------------------------------
        tf["5m"]  = self.builder_5m.get_series()   # solo velas cerradas
        tf["30m"] = self.builder_30m.get_series()  # solo velas cerradas
        tf["4h"]  = self.builder_4h.get_series()   # solo velas cerradas

        # ------------------------------------------------------------
        # 3. DETECCIÓN DE ESTRUCTURA 4H
        # ------------------------------------------------------------
        if len(tf["4h"]) >= 12:
            structure = self.structure_detector.detect(tf["4h"])
            tf["4h"][-1].structure = structure.get("trend")

        # ------------------------------------------------------------
        # 4. PREMIUM / DISCOUNT (30M)
        # ------------------------------------------------------------
        if len(tf["30m"]) >= 20:
            highs = [c.high for c in tf["30m"][-20:]]
            lows  = [c.low  for c in tf["30m"][-20:]]

            swing_high = max(highs)
            swing_low  = min(lows)
            mid = (swing_high + swing_low) / 2

            last_price = tf["30m"][-1].close

            tf["30m"][-1].premium  = last_price > mid
            tf["30m"][-1].discount = last_price < mid

        # ------------------------------------------------------------
        # 5. LIMPIEZA DE BUFFERS (CRÍTICO)
        # ------------------------------------------------------------
        if len(tf["1m"]) > 5000:
            tf["1m"] = tf["1m"][-2000:]

        if len(tf["5m"]) > 2000:
            tf["5m"] = tf["5m"][-800:]

        if len(tf["30m"]) > 1000:
            tf["30m"] = tf["30m"][-400:]

        if len(tf["4h"]) > 500:
            tf["4h"] = tf["4h"][-200:]

        # ------------------------------------------------------------
        # 6. LOG
        # ------------------------------------------------------------
        if BASIC_LOG_ONLY:
            return tf

        print("\n===== BIUMOLO — TF LOADER =====")
        print(f"1m:   {len(tf['1m'])} velas")
        print(f"5m:   {len(tf['5m'])} velas (cerradas)")
        print(f"30m:  {len(tf['30m'])} velas (cerradas)")
        print(f"4h:   {len(tf['4h'])} velas (cerradas)")
        print("================================\n")

        return tf
