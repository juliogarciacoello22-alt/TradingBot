"""
AUDITOR BIUMOLO PRO
-------------------
Revisa la salud completa del sistema:
- Delta
- Microestructura
- OBEngine
- ContextEngine
- TimingEngine PRO
- ForecastEngine
- SignalEngine V4 PRO
- RiskEngine v4 PRO
- ExecutionEngine PRO
- PipelineLive PRO
"""

import traceback
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
from core.pipeline_live_pro import PipelineLivePRO


# ============================================================
#   UTILIDAD: imprimir estado
# ============================================================
def ok(msg):
    print(f"[OK] {msg}")

def fail(msg):
    print(f"[FAIL] {msg}")

def info(msg):
    print(f"[INFO] {msg}")


# ============================================================
#   AUDITOR PRINCIPAL
# ============================================================
def audit_biumolo():

    print("\n=====================================")
    print("     🔍 AUDITOR BIUMOLO PRO")
    print("=====================================\n")

    # ------------------------------------------------------------
    # 1. Crear módulos
    # ------------------------------------------------------------
    try:
        reaction = ReactionLevelEngine()
        micro_engine = MicrostructureEngine()
        ob_engine = OBEngine()
        context_engine = ContextEngine()
        timing_engine = TimingEngine()
        forecast_engine = LiquidityForecastEngine()
        signal_engine = SignalEngineV4(reaction)
        risk_engine = RiskEngine()

        ok("Módulos cargados correctamente")
    except Exception as e:
        fail(f"Error cargando módulos: {e}")
        return

    # ------------------------------------------------------------
    # 2. Crear vela de prueba
    # ------------------------------------------------------------
    candle = type("Candle", (), {})()
    candle.open = 100
    candle.close = 101
    candle.high = 102
    candle.low = 99
    candle.volume = 500
    candle.timestamp = 1234567890

    ok("Vela de prueba generada")

    # ------------------------------------------------------------
    # 3. Delta
    # ------------------------------------------------------------
    try:
        d = delta_calc.compute_delta(candle)
        cd = delta_calc.compute_cumdelta([candle])
        ok(f"Delta OK → delta={d}, cumdelta={cd}")
    except Exception as e:
        fail(f"Delta roto: {e}")

    # ------------------------------------------------------------
    # 4. Microestructura
    # ------------------------------------------------------------
    try:
        micro = micro_engine.process(candle, delta=d, prev_delta=0)
        ok(f"Microestructura OK → {micro}")
    except Exception as e:
        fail(f"Microestructura rota: {e}")

    # ------------------------------------------------------------
    # 5. OBEngine
    # ------------------------------------------------------------
    try:
        ob = ob_engine.detect_ob([candle], micro)
        ok(f"OBEngine OK → {ob}")
    except Exception as e:
        fail(f"OBEngine roto: {e}")

    # ------------------------------------------------------------
    # 6. ContextEngine
    # ------------------------------------------------------------
    try:
        tf = {"1m": [candle], "5m": [candle], "30m": [candle], "4h": [candle]}
        context = context_engine.build_context(tf)
        ok(f"ContextEngine OK → {context}")
    except Exception as e:
        fail(f"ContextEngine roto: {e}")

    # ------------------------------------------------------------
    # 7. TimingEngine PRO
    # ------------------------------------------------------------
    try:
        timing = timing_engine.build_timing(tf)
        ok(f"TimingEngine PRO OK → {timing}")
    except Exception as e:
        fail(f"TimingEngine PRO roto: {e}")

    # ------------------------------------------------------------
    # 8. ForecastEngine
    # ------------------------------------------------------------
    try:
        forecast = forecast_engine.predict([candle], micro)
        ok(f"ForecastEngine OK → {forecast}")
    except Exception as e:
        fail(f"ForecastEngine roto: {e}")

    # ------------------------------------------------------------
    # 9. SignalEngine V4 PRO
    # ------------------------------------------------------------
    try:
        signal = signal_engine.build_signal(
            tf=tf,
            micro=micro,
            context=context,
            timing=timing,
            delta=d,
            forecast=forecast
        )
        ok(f"SignalEngine V4 PRO OK → {signal}")
    except Exception as e:
        fail(f"SignalEngine V4 PRO roto: {e}")

    # ------------------------------------------------------------
    # 10. RiskEngine v4 PRO
    # ------------------------------------------------------------
    try:
        if signal:
            risk = risk_engine.evaluate(micro, signal["side"], signal["meta"])
            ok(f"RiskEngine PRO OK → {risk}")
        else:
            info("SignalEngine no generó señal → RiskEngine no evaluado")
    except Exception as e:
        fail(f"RiskEngine PRO roto: {e}")

    # ------------------------------------------------------------
    # 11. ExecutionEngine PRO
    # ------------------------------------------------------------
    try:
        if signal:
            valid, reason = execution_engine.validate(
                tf=tf,
                micro=micro,
                signal=signal,
                context=context,
                timing=timing,
                delta={"delta": d, "cumdelta": cd}
            )
            ok(f"ExecutionEngine PRO OK → valid={valid}, reason={reason}")
        else:
            info("No hay señal → ExecutionEngine no evaluado")
    except Exception as e:
        fail(f"ExecutionEngine PRO roto: {e}")

    print("\n=====================================")
    print("     🟩 AUDITOR COMPLETADO")
    print("=====================================\n")


if __name__ == "__main__":
    audit_biumolo()
