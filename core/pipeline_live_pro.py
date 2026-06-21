# core/pipeline_live_pro.py

import time
import json
import os
import traceback

from core.reaction_level_engine import ReactionLevelEngine
from core.signal_engine_v4_pro import SignalEngineV4
from core.exit_engine import ExitEngine
from core.trade_logger_v2 import log_trade
from core.biumolo_logger import log
from core.timeframe_loader import TimeframeLoader
from core.microstructure_engine import MicrostructureEngine
from core.context_engine import ContextEngine
from core.timing_engine_pro import TimingEngine
from core.liquidity_forecast_engine import LiquidityForecastEngine
from core.risk_engine_v4_pro import RiskEngine
from core.execution_engine_pro import execution_engine
from core.delta import delta_calc
from core.dashboard import update_dashboard
from core.biumolo_file_logger import (
    log_institucional_file_basic,
    log_institucional_file_extended
)
from core.ob_engine import OBEngine
from core.dedup_engine import DeduplicationEngine
from core.biumolo_config import BASIC_LOG_ONLY


ACTIVATION_MINUTES = 0


class PipelineLivePRO:
    """
    PipelineLive PRO — ÚNICO pipeline productivo
    --------------------------------------------
    - Feed 1m → Timeframes
    - Delta PRO
    - Microestructura PRO
    - OB PRO
    - Context PRO
    - Timing PRO
    - Forecast PRO
    - SignalEngine V4 PRO
    - RiskEngine v4 PRO
    - ExecutionEngine PRO
    - Dedup PRO
    - Envío a Telegram / NinjaTrader
    """

    def __init__(self, api, is_live=True):
        self.api = api
        self.is_live = is_live  # 🔒 bloqueo institucional de envío
        self.reaction_engine = ReactionLevelEngine()
        self.micro_engine = MicrostructureEngine()
        self.context_engine = ContextEngine()
        self.timing_engine = TimingEngine()
        self.signal_engine = SignalEngineV4(self.reaction_engine)
        self.forecast_engine = LiquidityForecastEngine()
        self.risk_engine = RiskEngine()
        self.ob_engine = OBEngine()
        self.exit_engine = ExitEngine()
        self.dedup = DeduplicationEngine()
        self.activation_start = None

        if not hasattr(self.api, "loader"):
            self.api.loader = TimeframeLoader(self.api)
        if not hasattr(self.api, "prev_delta"):
            self.api.prev_delta = None

    # ------------------------------------------------------------
    # LOG DE SEÑALES
    # ------------------------------------------------------------
    def _log_signal(self, final_signal):
        os.makedirs("logs", exist_ok=True)
        path = os.path.join("logs", "signals.log")
        with open(path, "a") as f:
            f.write(json.dumps(final_signal) + "\n")

    # ------------------------------------------------------------
    # PROCESO PRINCIPAL
    # ------------------------------------------------------------
    def process(self, raw):
        try:
            if not BASIC_LOG_ONLY:
                print("PIPELINE LIVE PRO RECIBIO:", raw)

            # 0) PING
            if raw.get("ping") is True:
                return None

            # 1) SEÑAL MANUAL
            if "side" in raw and "entry" in raw and "stop" in raw:
                print(">> SEÑAL MANUAL RECIBIDA:", raw)

                valid, reason = execution_engine.validate(
                    tf={"1m": [], "5m": [], "30m": []},
                    micro={},
                    signal=raw,
                    context={},
                    timing={},
                    delta={}
                )

                if not valid:
                    print(">> SEÑAL MANUAL CANCELADA —", reason)
                    return None

                # 🔒 bloqueo por is_live
                if self.is_live:
                    self.api.send_signal(raw)
                    print(">> SEÑAL MANUAL ENVIADA")
                else:
                    print(">>> MODO HISTÓRICO — señal manual NO enviada")

                return raw

            # 2) VALIDAR VELA
            required = ["open", "high", "low", "close", "volume", "timestamp"]
            if not all(k in raw for k in required):
                return None

            # 3) TIMEFRAME LOADER
            tf = self.api.loader.load()

            # 4) WARMUP
            if ACTIVATION_MINUTES > 0:
                if self.activation_start is None:
                    self.activation_start = time.time()
                elapsed = (time.time() - self.activation_start) / 60
                if elapsed < ACTIVATION_MINUTES:
                    return None

            # 5) REQUISITOS MÍNIMOS
            if len(tf["1m"]) < 1 or len(tf["5m"]) < 3 or len(tf["30m"]) < 1:
                return None

            candle = tf["1m"][-1]

            # 6) GESTIÓN DE SALIDA
            if self.exit_engine.has_open_trade():
                trade_closed = self.exit_engine.check_exit(candle.close)
                if trade_closed:
                    log_trade(trade_closed)
                    print(">> TRADE CERRADO:", trade_closed)

            # 7) DELTA PRO
            delta_value = delta_calc.compute_delta(candle)
            cumdelta_value = delta_calc.compute_cumdelta(tf["1m"])

            delta = {
                "delta": delta_value,
                "cumdelta": cumdelta_value
            }

            # 8) MICROESTRUCTURA + OB
            micro = self.micro_engine.process(
                candle,
                delta=delta_value,
                prev_delta=self.api.prev_delta
            )
            micro["ob"] = self.ob_engine.detect_ob(tf["1m"], micro)

            log_institucional_file_basic(candle, micro)

            # 9) CONTEXTO
            context = self.context_engine.build_context(tf)

            # 10) TIMING PRO
            timing = self.timing_engine.build_timing(tf)

            # 11) FORECAST
            forecast = self.forecast_engine.predict(tf["1m"], micro) or {}

            # 12) SIGNAL ENGINE V4 PRO
            signal = self.signal_engine.build_signal(
                tf=tf,
                micro=micro,
                context=context,
                timing=timing,
                delta=delta_value,   # numérico
                forecast=forecast
            )

            # 13) ENRIQUECER META CON TIMING
            if signal:
                signal.setdefault("meta", {})
                signal["meta"]["timing"] = timing or {}

            # 14) RISK ENGINE v4 PRO + META.RISK NORMALIZADO
            if signal:
                side = signal.get("side")
                meta = signal.get("meta", {})

                risk = self.risk_engine.evaluate(micro, side, meta)

                risk_meta = {}
                if isinstance(risk, dict):
                    risk_meta = {
                        "valid": risk.get("valid"),
                        "score": risk.get("risk_score"),
                        "reason": risk.get("reason")
                    }

                signal.setdefault("meta", {})
                signal["meta"]["risk"] = risk_meta

                if isinstance(risk, dict) and not risk.get("valid", True):
                    print(">> SEÑAL CANCELADA POR RISKENGINE —", risk)
                    signal = None

            # 15) FILTRO POR TIMING
            if signal:
                if isinstance(timing, dict) and not timing.get("valid", True):
                    print(">> SEÑAL CANCELADA POR TIMINGENGINE —", timing.get("reason"))
                    signal = None

            # 16) VALIDACIÓN FINAL — EXECUTION ENGINE PRO
            final_signal = None

            if signal:
                valid, reason = execution_engine.validate(
                    tf=tf,
                    micro=micro,
                    signal=signal,
                    context=context,
                    timing=timing,
                    delta=delta      # dict {delta, cumdelta}
                )

                if valid:
                    final_signal = signal
                else:
                    print(">> SEÑAL RECHAZADA POR EXECUTIONENGINE —", reason)

            # 17) DASHBOARD
            update_dashboard(candle, micro, final_signal)

            # 18) LOG EXTENDIDO
            log_institucional_file_extended(
                candle,
                micro,
                context,
                timing,
                final_signal
            )

            # 19) LOG + DEDUP + ENVÍO + ABRIR TRADE
            if final_signal:

                if self.dedup.is_duplicate(final_signal):
                    print("⛔ Señal duplicada — descartada")
                else:
                    print("✔ Señal nueva — procesada")
                    self._log_signal(final_signal)

                    if self.is_live:
                        self.api.send_signal(final_signal)
                        self.exit_engine.open_from_signal(final_signal)
                        print(">> SEÑAL INSTITUCIONAL ENVIADA A TELEGRAM / NINJATRADER")
                    else:
                        print(">>> MODO HISTÓRICO — señal NO enviada, solo logueada")

            # actualizar prev_delta
            self.api.prev_delta = delta_value

            return final_signal

        except Exception as e:
            print("ERROR EN PIPELINE LIVE PRO:", e)
            traceback.print_exc()
            return None
