import asyncio
import json
import os
import types
import sys

# 🔥 FIX REAL PARA WINDOWS
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.delta import delta_calc
from core.microstructure_engine import MicrostructureEngine
from core.ob_engine import OBEngine
from core.context_engine import ContextEngine
from core.timing_engine_pro import TimingEngine
from core.liquidity_forecast_engine import LiquidityForecastEngine
from core.signal_engine_v4_pro import SignalEngineV4
from core.reaction_level_engine import ReactionLevelEngine
from core.risk_engine_v4_pro import RiskEngine
from core.execution_engine_pro import execution_engine
from core.api import API


LINE = "=" * 37


def print_header():
    print(LINE)
    print("     🔍 AUDITOR BIUMOLO PRO v2")
    print(LINE)
    print()


# -----------------------------
# Helpers de velas deterministas
# -----------------------------
class Candle:
    def __init__(self, o, h, l, c, v, ts):
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v
        self.timestamp = ts
        self.isClosed = True

        # 🔥 NECESARIO PARA OBEngine
        self.range = self.high - self.low
        self.body = abs(self.close - self.open)
        self.wick_up = self.high - max(self.close, self.open)
        self.wick_down = min(self.close, self.open) - self.low


def build_tf_1m_scenario():
    """
    Construye un pequeño set de velas 1m deterministas para:
    - generar delta
    - permitir OB
    - permitir microestructura
    """
    candles = [
        Candle(100, 101, 99.5, 100.5, 100, 1),
        Candle(100.5, 102, 100.4, 101.8, 150, 2),
        Candle(101.8, 103, 101.7, 102.9, 200, 3),
        Candle(102.9, 103.5, 102.0, 102.2, 180, 4),
    ]
    return candles


def build_tf_multi():
    tf1m = build_tf_1m_scenario()
    # para 5m y 30m usamos placeholders simples
    tf5m = tf1m[-3:]
    tf30m = tf1m[-1:]
    tf4h = tf1m[-1:]
    return {
        "1m": tf1m,
        "5m": tf5m,
        "30m": tf30m,
        "4h": tf4h,
    }


# -----------------------------
# Stubs para Telegram y NinjaTrader
# -----------------------------
class FakeTelegram:
    def __init__(self):
        self.sent_messages = []

    def send(self, msg):
        self.sent_messages.append(msg)
        print("[TELEGRAM STUB] Mensaje capturado")


class FakeWebSocket:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(text)
        print("[WS STUB] Señal enviada (simulada)")


# -----------------------------
# Test 1: Delta + CumDelta real
# -----------------------------
def test_delta_and_cumdelta():
    print("[TEST] Delta + CumDelta con velas isClosed=True")

    tf = build_tf_1m_scenario()
    last_candle = tf[-1]

    d = delta_calc.compute_delta(last_candle)
    cd = delta_calc.compute_cumdelta(tf)

    print(f"  delta={d}")
    print(f"  cumdelta={cd}")

    if cd == 0:
        print("[WARN] cumdelta=0 → revisar lógica de DeltaCalculator para histórico")
    else:
        print("[OK] CumDelta distinto de cero → respeta velas cerradas")


# -----------------------------
# Test 2: Microestructura + OB
# -----------------------------
def test_micro_and_ob():
    print("\n[TEST] Microestructura + OBEngine")

    tf = build_tf_multi()
    micro_engine = MicrostructureEngine()
    ob_engine = OBEngine()

    prev_delta = None
    last_candle = tf["1m"][-1]
    d = delta_calc.compute_delta(last_candle)

    micro = micro_engine.process(
        last_candle,
        delta=d,
        prev_delta=prev_delta
    )
    micro["ob"] = ob_engine.detect_ob(tf["1m"], micro)

    print("  micro:", micro)

    if micro.get("ob") is None:
        print("[INFO] OB no generado en este escenario (no es error)")
    else:
        print("[OK] OB generado:", micro["ob"])


# -----------------------------
# Test 3: Context + Timing + Forecast
# -----------------------------
def test_context_timing_forecast():
    print("\n[TEST] ContextEngine + TimingEngine + ForecastEngine")

    tf = build_tf_multi()
    context_engine = ContextEngine()
    timing_engine = TimingEngine()
    forecast_engine = LiquidityForecastEngine()

    context = context_engine.build_context(tf)
    timing = timing_engine.build_timing(tf)
    forecast = forecast_engine.predict(tf["1m"], {}) or {}

    print("  context:", context)
    print("  timing:", timing)
    print("  forecast:", forecast)

    if context.get("trend_4h") is None:
        print("[WARN] trend_4h=None → revisar contrato con ExecutionEngine")
    else:
        print("[OK] ContextEngine devolvió trend_4h:", context.get("trend_4h"))

    if not timing.get("valid", False):
        print("[WARN] TimingEngine marcó invalid → revisar condiciones")
    else:
        print("[OK] TimingEngine valid=True, session:", timing.get("session"))


# -----------------------------
# Test 4: SignalEngine + Risk + Execution
# -----------------------------
def test_signal_risk_execution():
    print("\n[TEST] SignalEngine V4 PRO + RiskEngine + ExecutionEngine")

    tf = build_tf_multi()
    reaction_engine = ReactionLevelEngine()
    signal_engine = SignalEngineV4(reaction_engine)
    micro_engine = MicrostructureEngine()
    context_engine = ContextEngine()
    timing_engine = TimingEngine()
    forecast_engine = LiquidityForecastEngine()
    risk_engine = RiskEngine()

    last_candle = tf["1m"][-1]
    d = delta_calc.compute_delta(last_candle)
    micro = micro_engine.process(last_candle, delta=d, prev_delta=None)
    context = context_engine.build_context(tf)
    timing = timing_engine.build_timing(tf)
    forecast = forecast_engine.predict(tf["1m"], micro) or {}

    signal = signal_engine.build_signal(
        tf=tf,
        micro=micro,
        context=context,
        timing=timing,
        delta=d,
        forecast=forecast
    )

    if signal is None:
        print("[INFO] SignalEngine no generó señal en este escenario (no es fallo de código)")
        return

    print("  signal:", signal)

    # Enriquecer meta como en PipelineLivePRO
    signal.setdefault("meta", {})
    signal["meta"]["timing"] = timing or {}

    side = signal.get("side")
    meta = signal.get("meta", {})

    risk = risk_engine.evaluate(micro, side, meta)
    print("  risk:", risk)

    if isinstance(risk, dict) and not risk.get("valid", True):
        print("[INFO] RiskEngine invalidó la señal → escenario conservador, no error de implementación")
        return

    # Normalizar como en pipeline
    risk_meta = {
        "valid": risk.get("valid"),
        "score": risk.get("risk_score"),
        "reason": risk.get("reason")
    }
    signal["meta"]["risk"] = risk_meta

    # ExecutionEngine
    delta_dict = {
        "delta": d,
        "cumdelta": delta_calc.compute_cumdelta(tf["1m"])
    }

    valid, reason = execution_engine.validate(
        tf=tf,
        micro=micro,
        signal=signal,
        context=context,
        timing=timing,
        delta=delta_dict
    )

    print("  execution_valid:", valid, "reason:", reason)

    if valid:
        print("[OK] ExecutionEngine aceptó la señal")
    else:
        print("[INFO] ExecutionEngine rechazó la señal en este escenario → revisar condiciones, no crash")


def test_execution_with_forced_contexts():
    print("\n[TEST] ExecutionEngine con trend_4h neutral vs bullish")

    tf = build_tf_multi()
    last_candle = tf["1m"][-1]
    d = delta_calc.compute_delta(last_candle)

    micro = {}
    timing = {"valid": True}
    delta_dict = {"delta": d, "cumdelta": delta_calc.compute_cumdelta(tf["1m"])}

    # 🔥 RR ahora es 1.5 → suficiente para pasar el filtro
    base_signal = {
        "side": "BUY",
        "entry": last_candle.close,
        "stop": last_candle.close - 1,
        "tp1": last_candle.close + 1.5,
        "tp2": last_candle.close + 2,
        "tp3": last_candle.close + 3,
        "meta": {}
    }

    # Context neutral
    context_neutral = {"trend_4h": "neutral"}
    v1, r1 = execution_engine.validate(
        tf=tf,
        micro=micro,
        signal=base_signal,
        context=context_neutral,
        timing=timing,
        delta=delta_dict
    )
    print("  neutral → valid:", v1, "reason:", r1)

    # Context bullish
    context_bull = {"trend_4h": "bullish"}
    v2, r2 = execution_engine.validate(
        tf=tf,
        micro=micro,
        signal=base_signal,
        context=context_bull,
        timing=timing,
        delta=delta_dict
    )
    print("  bullish → valid:", v2, "reason:", r2)
async def test_api_send_signal():
    print("\n[TEST] API.send_signal + JSON + Telegram + NinjaTrader")

    # Crear instancia sin ejecutar __init__
    api = API.__new__(API)

    # Inyectar stubs
    fake_telegram = FakeTelegram()
    fake_ws = FakeWebSocket()

    api.telegram = fake_telegram
    api.ws = fake_ws

    signal = {
        "side": "BUY",
        "entry": 100.0,
        "stop": 99.0,
        "tp1": 101.0,
        "tp2": 102.0,
        "tp3": 103.0,
        "meta": {
            "micro": {"sweep": "up"},
            "context": {"trend_4h": "bullish"},
            "timing": {"session": "london", "valid": True},
            "risk": {"valid": True, "score": 5, "reason": "test"}
        }
    }

    # JSON serializable
    try:
        json.dumps(signal)
        print("[OK] Señal JSON serializable")
    except Exception as e:
        print("[ERROR] Señal NO es JSON serializable:", e)
        return

    # Enviar
    await api.send_signal(signal)

    if not fake_telegram.sent_messages:
        print("[ERROR] Telegram stub no recibió mensaje")
    else:
        print("[OK] Telegram stub recibió mensaje")

    if not fake_ws.sent:
        print("[ERROR] WebSocket stub no recibió señal")
    else:
        print("[OK] WebSocket stub recibió señal (ACK simulado)")


# -----------------------------
# MAIN
# -----------------------------
def main():
    print_header()

    print("[INFO] Iniciando auditoría profunda BIUMOLO PRO v2\n")

    test_delta_and_cumdelta()
    test_micro_and_ob()
    test_context_timing_forecast()
    test_signal_risk_execution()
    test_execution_with_forced_contexts()

    asyncio.run(test_api_send_signal())

    print("\n" + LINE)
    print("     🟩 AUDITOR v2 COMPLETADO")
    print(LINE)


if __name__ == "__main__":
    main()
