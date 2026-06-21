# core/delta.py
from datetime import datetime, timedelta, timezone


class DeltaCalculator:
    """
    DeltaCalculator PRO — Institucional + Real + Proxy + Sesión CME
    ---------------------------------------------------------------
    - Delta real: ask_volume - bid_volume
    - Delta proxy: (close - open) / (high - low) * volume
    - Auto-switch: usa delta real si existe, proxy si no
    - CumDelta institucional sin retraso
    - Reseteo por sesión CME (16:00)
    - Manejo automático de CST/CDT
    - Siempre devuelve float (nunca None)
    """

    def __init__(self, session_close_hour=16):
        self.session_close_hour = session_close_hour

    # ============================================================
    #   DETECTAR OFFSET HORARIO CME (CST/CDT)
    # ============================================================
    def _detect_cme_tz(self, ts: datetime):
        if 3 <= ts.month <= 11:
            return timezone(timedelta(hours=-5))  # CDT
        return timezone(timedelta(hours=-6))      # CST

    # ============================================================
    #   DELTA REAL (ask - bid) O PROXY OHLCV
    # ============================================================
    def compute_delta(self, candle):
        if candle is None:
            return 0.0

        if candle.open is None or candle.close is None:
            return 0.0
        if candle.high is None or candle.low is None:
            return 0.0
        if candle.volume is None or candle.volume < 0:
            return 0.0

        # 1. DELTA REAL
        ask_v = getattr(candle, "ask_volume", None)
        bid_v = getattr(candle, "bid_volume", None)

        if ask_v is not None and bid_v is not None:
            return float(ask_v - bid_v)

        # 2. DELTA PROXY
        price_move = candle.close - candle.open
        range_ = candle.high - candle.low

        if range_ == 0:
            return 0.0

        return float((price_move / range_) * candle.volume)

    # ============================================================
    #   CUMULATIVE DELTA INSTITUCIONAL (REAL O PROXY)
    # ============================================================
    def compute_cumdelta(self, candles):
        if not candles:
            return 0.0

        cum = 0.0
        last_session = None

        for c in candles:

            if not getattr(c, "isClosed", False):
                continue

            ts = getattr(c, "timestamp", None)
            if ts is None:
                continue

            # Normalizar timestamp
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            elif isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            else:
                continue

            # Detectar zona CME
            session_tz = self._detect_cme_tz(ts)
            ts = ts.astimezone(session_tz)

            # Clave de sesión
            session_key = ts.date()

            # 16:00 CME → cierre de sesión
            if ts.hour < self.session_close_hour or (
                ts.hour == self.session_close_hour and ts.minute == 0 and ts.second == 0
            ):
                session_key = session_key - timedelta(days=1)

            # Reinicio de sesión
            if last_session is None or session_key != last_session:
                cum = 0.0
                last_session = session_key

            # Delta actual
            delta = self.compute_delta(c)
            cum += delta

        return float(cum)


# instancia global
delta_calc = DeltaCalculator()
