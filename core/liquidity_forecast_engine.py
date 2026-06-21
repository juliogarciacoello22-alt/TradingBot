# core/liquidity_forecast_engine.py

class LiquidityForecastEngine:
    """
    Liquidity Forecast Engine PRO — BIUMOLO INSTITUCIONAL
    -----------------------------------------------------
    Predice:
    - Liquidez futura (EQH/EQL)
    - Sweeps probables
    - Inducement futuro
    - Zonas probables de BOS/CHOCH
    - Zonas probables de futuros OB/FVG
    - Compatible con Microestructura PRO
    """

    def __init__(self):
        self.last_forecast = None

    # ============================================================
    #   API PRINCIPAL
    # ============================================================
    def predict(self, candles, micro):
        # mínimo institucional
        if len(candles) < 10:
            forecast = self._empty()
            self.last_forecast = forecast
            return forecast

        # swings institucionales PRO
        swing = micro.get("swing", {})
        swing_high = swing.get("high")
        swing_low  = swing.get("low")

        # validar swings
        if not swing_high or not swing_low:
            forecast = self._empty()
            self.last_forecast = forecast
            return forecast

        if "price" not in swing_high or "price" not in swing_low:
            forecast = self._empty()
            self.last_forecast = forecast
            return forecast

        sh = swing_high["price"]
        sl = swing_low["price"]

        # rango institucional
        range_ = sh - sl
        if range_ <= 0:
            forecast = self._empty()
            self.last_forecast = forecast
            return forecast

        offset = range_ * 0.15

        # liquidez futura
        future_eqh = sh + offset
        future_eql = sl - offset

        # sweeps probables
        future_sweep_up   = future_eqh
        future_sweep_down = future_eql

        # inducement forecast PRO
        inducement = self._forecast_inducement(micro, future_eqh, future_eql)

        # BOS/CHOCH zones PRO
        bos_choch = self._forecast_bos_choch(swing_high, swing_low, future_eqh, future_eql)

        # futuros OB/FVG PRO
        future_ob_fvg = self._forecast_ob_fvg(candles, micro, future_eqh, future_eql)

        forecast = {
            "future_eqh": future_eqh,
            "future_eql": future_eql,
            "future_sweep_up": future_sweep_up,
            "future_sweep_down": future_sweep_down,
            "inducement": inducement,
            "bos_choch_zones": bos_choch,
            "future_ob_fvg": future_ob_fvg
        }

        self.last_forecast = forecast
        return forecast

    # ============================================================
    #   FORECAST VACÍO
    # ============================================================
    def _empty(self):
        return {
            "future_eqh": None,
            "future_eql": None,
            "future_sweep_up": None,
            "future_sweep_down": None,
            "inducement": None,
            "bos_choch_zones": None,
            "future_ob_fvg": None
        }

    # ============================================================
    #   INDUCEMENT FORECAST PRO
    # ============================================================
    def _forecast_inducement(self, micro, future_eqh, future_eql):
        disp = micro.get("displacement")
        compression = micro.get("compression")
        liquidity = micro.get("liquidity", {}) or {}

        eqh = liquidity.get("eqh")
        eql = liquidity.get("eql")

        inducement_up = None
        inducement_down = None
        strength = 0

        # compresión + liquidez → inducement
        if compression and eqh:
            inducement_up = future_eqh
            strength += 1

        if compression and eql:
            inducement_down = future_eql
            strength += 1

        # displacement contra liquidez → inducement fuerte
        if disp == "up" and eql:
            inducement_down = future_eql
            strength += 1

        if disp == "down" and eqh:
            inducement_up = future_eqh
            strength += 1

        return {
            "inducement_up": inducement_up,
            "inducement_down": inducement_down,
            "strength": strength
        }

    # ============================================================
    #   BOS / CHOCH FORECAST PRO
    # ============================================================
    def _forecast_bos_choch(self, swing_high, swing_low, future_eqh, future_eql):
        sh = swing_high["price"]
        sl = swing_low["price"]

        # zonas institucionales
        bos_up_zone   = (future_eqh, future_eqh * 1.01)
        bos_down_zone = (future_eql * 0.99, future_eql)

        choch_up_zone   = (sh * 0.995, sh * 1.005)
        choch_down_zone = (sl * 0.995, sl * 1.005)

        return {
            "bos_up_zone": bos_up_zone,
            "bos_down_zone": bos_down_zone,
            "choch_up_zone": choch_up_zone,
            "choch_down_zone": choch_down_zone
        }

    # ============================================================
    #   FUTUROS OB / FVG PRO
    # ============================================================
    def _forecast_ob_fvg(self, candles, micro, future_eqh, future_eql):
        disp = micro.get("displacement")
        absorption = micro.get("absorption")
        expansion = micro.get("expansion")

        last = candles[-1]
        prev = candles[-2]

        base_range = (prev.high - prev.low) * 0.5

        future_ob_bullish = None
        future_ob_bearish = None
        future_fvg_bullish = None
        future_fvg_bearish = None

        # OB/FVG alcista institucional
        if disp == "up" and absorption == "buy" and expansion:
            future_ob_bullish = (prev.open, prev.low)
            future_fvg_bullish = (last.high, last.high + base_range)

        # OB/FVG bajista institucional
        if disp == "down" and absorption == "sell" and expansion:
            future_ob_bearish = (prev.high, prev.open)
            future_fvg_bearish = (last.low - base_range, last.low)

        return {
            "future_ob_bullish": future_ob_bullish,
            "future_ob_bearish": future_ob_bearish,
            "future_fvg_bullish": future_fvg_bullish,
            "future_fvg_bearish": future_fvg_bearish
        }
