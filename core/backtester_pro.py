# core/backtester_pro.py

from core.microstructure_engine import MicrostructureEngine
from core.signal_engine_v4 import SignalEngineV4
from core.reaction_level_engine import ReactionLevelEngine
from core.liquidity_forecast_engine import LiquidityForecastEngine
from core.context_engine import ContextEngine
from core.timing_engine import TimingEngine
from core.ob_engine import OBEngine
from core.tp_engine import TPEngine


class BacktesterPRO:

    def __init__(self, feed):
        self.feed = feed

        # Motores institucionales
        self.micro_engine    = MicrostructureEngine()
        self.reaction_engine = ReactionLevelEngine()
        self.signal_engine   = SignalEngineV4(self.reaction_engine)
        self.forecast_engine = LiquidityForecastEngine()
        self.context_engine  = ContextEngine()
        self.timing_engine   = TimingEngine()
        self.ob_engine       = OBEngine()
        self.tp_engine       = TPEngine()

        # Estado
        self.prev_delta = None
        self.trades = []

        # TF internos (histórico)
        self.tf = {
            "1m": [],
            "5m": [],
            "30m": [],
            "4h": []
        }

    # ============================================================
    #   ACTUALIZAR TIMEFRAMES (BACKTEST)
    # ============================================================
    def _update_tf(self, candle):
        self.tf["1m"].append(candle)

    # ============================================================
    #   PROCESAR UNA VELA
    # ============================================================
    def process_candle(self, candle):

        # 1. Actualizar TF
        self._update_tf(candle)

        # 2. Delta histórico
        delta = getattr(candle, "delta", None)
        cumdelta = getattr(candle, "cumdelta", None)

        # 3. Microestructura PRO
        micro = self.micro_engine.process(
            candle,
            delta=delta,
            prev_delta=self.prev_delta
        )

        # 4. OB institucional
        micro["ob"] = self.ob_engine.detect_ob(self.tf["1m"], micro)

        # 5. Contexto institucional (4H, sesión, etc.)
        context = self.context_engine.build_context(self.tf)

        # 6. Timing institucional
        timing = self.timing_engine.build_timing(self.tf)

        # 7. Forecast institucional
        forecast = self.forecast_engine.predict(self.tf["1m"], micro)

        # 8. Señal institucional PRO
        signal = self.signal_engine.build_signal(
            tf=self.tf,
            micro=micro,
            context=context,
            timing=timing,
            delta=delta,
            forecast=forecast
        )

        # 9. Abrir trade si hay señal
        if signal:
            self._open_trade(signal, candle, micro, delta, cumdelta)

        # 10. Actualizar prev_delta
        self.prev_delta = delta

    # ============================================================
    #   ABRIR TRADE
    # ============================================================
    def _open_trade(self, signal, candle, micro, delta, cumdelta):

        trade = {
            "side": signal["side"],
            "mode": signal["mode"],
            "entry": signal["entry"],
            "stop": signal["stop"],
            "tp1": signal["tp1"],
            "tp2": signal["tp2"],
            "tp3": signal["tp3"],

            # DELTA PRO EN ENTRY
            "delta_entry": delta,
            "prev_delta_entry": self.prev_delta,
            "cumdelta_entry": cumdelta,

            # MICRO PRO EN ENTRY
            "displacement": micro.get("displacement"),
            "momentum": micro.get("momentum"),
            "inducement": micro.get("inducement"),
            "fake_displacement": micro.get("fake_displacement"),
            "absorption": micro.get("absorption"),
            "breaker": micro.get("breaker"),

            # RAZONES
            "reason": signal.get("reason"),
            "ob": signal.get("ob"),

            # ESTADO
            "open": True,
            "result": None
        }

        self.trades.append(trade)

    # ============================================================
    #   CERRAR TRADE
    # ============================================================
    def close_trade(self, trade, candle):

        delta = getattr(candle, "delta", None)
        cumdelta = getattr(candle, "cumdelta", None)

        trade["open"] = False
        trade["delta_exit"] = delta
        trade["cumdelta_exit"] = cumdelta

        if trade["side"] == "BUY":
            if candle.low <= trade["stop"]:
                trade["result"] = "SL"
            elif candle.high >= trade["tp3"]:
                trade["result"] = "TP3"
            elif candle.high >= trade["tp2"]:
                trade["result"] = "TP2"
            elif candle.high >= trade["tp1"]:
                trade["result"] = "TP1"
            else:
                trade["result"] = "NONE"
        else:
            if candle.high >= trade["stop"]:
                trade["result"] = "SL"
            elif candle.low <= trade["tp3"]:
                trade["result"] = "TP3"
            elif candle.low <= trade["tp2"]:
                trade["result"] = "TP2"
            elif candle.low <= trade["tp1"]:
                trade["result"] = "TP1"
            else:
                trade["result"] = "NONE"

        return trade
