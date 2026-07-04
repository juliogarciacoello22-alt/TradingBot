import os
import json
import time
import traceback

from core.reaction_level_engine import ReactionLevelEngine
from core.signal_engine_v4 import SignalEngineV4
from core.exit_engine import ExitEngine
from core.trade_logger_v2 import log_trade
from core.biumolo_logger import log
from core.timeframe_loader import TimeframeLoader
from core.microstructure_engine import MicrostructureEngine
from core.context_engine import ContextEngine
from core.timing_engine import TimingEngine
from core.liquidity_forecast_engine import LiquidityForecastEngine
from core.risk_engine_v4 import RiskEngine
from core.execution_engine import execution_engine
from core.delta import delta_calc
from core.dashboard import update_dashboard
from core.biumolo_file_logger import (
    log_institucional_file_basic,
    log_institucional_file_extended
)
from core.ob_engine import OBEngine
from core.dedup_engine import DeduplicationEngine

dedup = DeduplicationEngine()

ACTIVATION_MINUTES = 0
activation_start = None

reaction_engine  = ReactionLevelEngine()
micro_engine     = MicrostructureEngine()
context_engine   = ContextEngine()
timing_engine    = TimingEngine()
signal_engine    = SignalEngineV4(reaction_engine)
forecast_engine  = LiquidityForecastEngine()
risk_engine      = RiskEngine()
ob_engine        = OBEngine()
exit_engine      = ExitEngine()


def log_signal(final_signal):
    os.makedirs("logs", exist_ok=True)
    path = os.path.join("logs", "signals.log")
    with open(path, "a") as f:
        f.write(json.dumps(final_signal) + "\n")


def backend(api, raw):
    global activation_start

    try:
        print("BACKEND RECIBIO:", raw)

        # ============================================================
        #   0. PING
        # ============================================================
        if raw.get("ping") is True:
            return None

        # ============================================================
        #   1. SEÑAL MANUAL INSTITUCIONAL
        # ============================================================
        if "side" in raw and "entry" in raw and "stop" in raw:
            print(">> SENAL MANUAL RECIBIDA:", raw)

            valid, reason = execution_engine.validate(
                tf={"1m": [], "5m": [], "30m": []},
                micro={},
                signal=raw,
                context={},
                timing={},
                delta={}
            )

            if not valid:
                print(">> SENAL MANUAL CANCELADA -", reason)
                return None

            api.send_signal(raw)
            print(">> SENAL MANUAL ENVIADA")
            return raw

        # ============================================================
        #   2. VALIDAR VELA
        # ============================================================
        required = ["open", "high", "low", "close", "volume", "timestamp"]
        if not all(k in raw for k in required):
            return None

        # ============================================================
        #   3. TIMEFRAME LOADER
        # ============================================================
        if not hasattr(api, "loader"):
            api.loader = TimeframeLoader(api)

        tf = api.loader.load()

        # ============================================================
        #   4. WARMUP
        # ============================================================
        if ACTIVATION_MINUTES > 0:
            if activation_start is None:
                activation_start = time.time()

            elapsed = (time.time() - activation_start) / 60
            if elapsed < ACTIVATION_MINUTES:
                return None

        # ============================================================
        #   5. REQUISITOS MÍNIMOS
        # ============================================================
        if len(tf["1m"]) < 1 or len(tf["5m"]) < 3 or len(tf["30m"]) < 1:
            return None

        candle = tf["1m"][-1]

        # ============================================================
        #   6. GESTIÓN DE SALIDA
        # ============================================================
        if exit_engine.has_open_trade():
            trade_closed = exit_engine.check_exit(candle.close)
            if trade_closed:
                log_trade(trade_closed)
                print(">> TRADE CERRADO:", trade_closed)

        # ============================================================
        #   7. DELTA (primero)
        # ============================================================
        if not hasattr(api, "prev_delta"):
            api.prev_delta = None

        delta_value = delta_calc.compute_delta(candle)
        cumdelta_value = delta_calc.compute_cumdelta(tf["1m"])

        delta = {
            "delta": delta_value,
            "cumdelta": cumdelta_value
        }

        # ============================================================
        #   8. MICROESTRUCTURA + OB (con delta PRO)
        # ============================================================
        micro = micro_engine.process(
            candle,
            delta=delta_value,
            prev_delta=api.prev_delta
        )
        micro["ob"] = ob_engine.detect_ob(tf["1m"], micro)

        log_institucional_file_basic(candle, micro)

        # ============================================================
        #   9. CONTEXTO HTF
        # ============================================================
        context = context_engine.build_context(tf)

        # ============================================================
        #   10. TIMING
        # ============================================================
        timing = timing_engine.build_timing(tf)

        # ============================================================
        #   11. FORECAST
        # ============================================================
        forecast = forecast_engine.predict(tf["1m"], micro) or {}

        # ============================================================
        #   12. SIGNAL ENGINE v4 (delta numérico)
        # ============================================================
        signal = signal_engine.build_signal(
            tf=tf,
            micro=micro,
            context=context,
            timing=timing,
            delta=delta_value,   # numérico, no dict
            forecast=forecast
        )

        # ============================================================
        #   13. RISK ENGINE v4
        # ============================================================
        if signal:
            side = signal.get("side")
            meta = signal.get("meta", {})

            risk = risk_engine.evaluate(micro, side, meta)
            signal.setdefault("meta", {})
            signal["meta"]["risk"] = risk

            if isinstance(risk, dict) and not risk.get("valid", True):
                print(">> SENAL CANCELADA POR RISKENGINE -", risk)
                signal = None


        # ============================================================
        #   14. FILTRO POR TIMING
        # ============================================================
        if signal:
            if isinstance(timing, dict) and not timing.get("valid", True):
                print(">> SENAL CANCELADA POR TIMINGENGINE - timing invalido")
                signal = None

        # ============================================================
        #   15. VALIDACIÓN FINAL
        # ============================================================
        final_signal = None

        if signal:
            valid, reason = execution_engine.validate(
                tf=tf,
                micro=micro,
                signal=signal,
                context=context,
                timing=timing,
                delta=delta      # aquí sí pasa el dict {delta, cumdelta}
            )

            if valid:
                final_signal = signal
            else:
                print(">> SENAL RECHAZADA POR EXECUTIONENGINE -", reason)

        # ============================================================
        #   16. DASHBOARD
        # ============================================================
        update_dashboard(candle, micro, final_signal)

        # ============================================================
        #   17. LOG EXTENDIDO
        # ============================================================
        log_institucional_file_extended(
            candle,
            micro,
            context,
            timing,
            final_signal
        )

        # ============================================================
        #   18. LOG + DEDUP + ENVÍO + ABRIR TRADE
        # ============================================================
        if final_signal:

            # DEDUP INSTITUCIONAL
            if dedup.is_duplicate(final_signal):
                print("BLOCKED Senal duplicada - descartada")
            else:
                print("OK Senal nueva - enviada")
                log_signal(final_signal)
                api.send_signal(final_signal)
                exit_engine.open_from_signal(final_signal)
                print(">> SENAL INSTITUCIONAL ENVIADA A TELEGRAM")

        # actualizar prev_delta SOLO si todo llegó aquí
        api.prev_delta = delta_value

        return final_signal

    except Exception as e:
        print("ERROR EN BACKEND:", e)
        traceback.print_exc()
        return None
