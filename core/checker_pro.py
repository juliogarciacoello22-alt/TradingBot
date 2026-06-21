# core/checker_pro.py

from core.candle import Candle
from core.microstructure_engine import MicrostructureEngine
from core.ob_engine import OBEngine
from core.reaction_level_engine import ReactionLevelEngine
from core.signal_engine_v4 import SignalEngineV4
from core.context_engine import ContextEngine
from core.timing_engine import TimingEngine
from core.liquidity_forecast_engine import LiquidityForecastEngine
from core.delta import delta_calc


class CheckerPRO:
    """
    Checker PRO — Auditoría Institucional Completa
    ----------------------------------------------
    - Valida Candle PRO
    - Valida Feed PRO
    - Valida Microestructura PRO
    - Valida SignalEngine PRO
    - Valida ReactionEngine PRO
    - Valida OBEngine
    - Valida pipeline completo
    """

    def __init__(self):
        self.micro = MicrostructureEngine()
        self.ob_engine = OBEngine()
        self.reaction = ReactionLevelEngine()
        self.signal = SignalEngineV4(self.reaction)
        self.context = ContextEngine()
        self.timing = TimingEngine()
        self.forecast = LiquidityForecastEngine()

        self.prev_delta = None
        self.candles = []
        self.tf = {"1m": self.candles}

    # ============================================================
    #   VALIDAR UNA VELA
    # ============================================================
    def validate_candle(self, c):
        errors = []

        if c.open is None or c.close is None:
            errors.append("OHLC inválido")

        if c.high < c.low:
            errors.append("High < Low")

        if c.volume is None or c.volume < 0:
            errors.append("Volumen inválido")

        if c.delta is None:
            errors.append("Delta no asignado")

        if c.cumdelta is None:
            errors.append("CumDelta no asignado")

        return errors

    # ============================================================
    #   PROCESAR UNA VELA
    # ============================================================
    def process(self, raw):

        c = Candle(raw)

        # delta
        c.delta = delta_calc.compute_delta(c)
        c.prev_delta = self.prev_delta
        c.cumdelta = (self.candles[-1].cumdelta if self.candles else 0) + (c.delta or 0)

        self.prev_delta = c.delta
        self.candles.append(c)

        # validar vela
        candle_errors = self.validate_candle(c)

        # microestructura
        micro = self.micro.process(c, delta=c.delta, prev_delta=c.prev_delta)

        # OB
        micro["ob"] = self.ob_engine.detect_ob(self.candles, micro)

        # contexto
        context = self.context.build_context(self.tf)

        # timing
        timing = self.timing.build_timing(self.tf)

        # forecast
        forecast = self.forecast.predict(self.candles, micro)

        # señal
        signal = self.signal.build_signal(
            tf=self.tf,
            micro=micro,
            context=context,
            timing=timing,
            delta=c.delta,
            forecast=forecast
        )

        # reacción
        reaction = None
        if signal:
            reaction = self.reaction.evaluate(
                signal["side"],
                c.close,
                {"micro": micro, "delta": c.delta, "cumdelta": c.cumdelta}
            )

        return {
            "candle": c,
            "candle_errors": candle_errors,
            "micro": micro,
            "signal": signal,
            "reaction": reaction,
            "context": context,
            "timing": timing,
            "forecast": forecast
        }
