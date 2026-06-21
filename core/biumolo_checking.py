# ============================================================
#   BIUMOLO CHECKING INSTITUCIONAL V4
#   Verifica:
#   - Microestructura
#   - OB Engine
#   - Reaction Engine
#   - Signal Engine V4
#   - Forecast
#   - Timing
#   - Contexto
# ============================================================

from core.microstructure_engine import MicrostructureEngine
from core.ob_engine import OBEngine
from core.reaction_level_engine import ReactionLevelEngine
from core.signal_engine_v4 import SignalEngineV4
from core.liquidity_forecast_engine import LiquidityForecastEngine
from core.timing_engine import TimingEngine
from core.context_engine import ContextEngine
from core.tp_engine import TPEngine
from core.candle import Candle

import random
import time


class BiumoloChecking:

    def __init__(self):
        self.micro = MicrostructureEngine()
        self.ob_engine = OBEngine()
        self.reaction = ReactionLevelEngine()
        self.signal = SignalEngineV4(self.reaction)
        self.forecast_engine = LiquidityForecastEngine()
        self.timing = TimingEngine()
        self.context = ContextEngine()

        self.candles = []
        self.tf = {"1m": self.candles}

    # ============================================================
    #   GENERAR VELA RANDOM (para test)
    # ============================================================
    def _random_candle(self, last_price):
        high = last_price + random.uniform(0.5, 2.0)
        low = last_price - random.uniform(0.5, 2.0)
        open_ = random.uniform(low, high)
        close = random.uniform(low, high)
        return Candle(open_, high, low, close, True)

    # ============================================================
    #   CHECKING COMPLETO
    # ============================================================
    def run(self, steps=50):

        print("\n==============================")
        print("   BIUMOLO CHECKING V4")
        print("==============================\n")

        last_price = 100.0

        for i in range(steps):

            # 1. Generar vela
            c = self._random_candle(last_price)
            last_price = c.close
            self.candles.append(c)

            # 2. Microestructura
            micro = self.micro.process(c)

            # 3. OB institucional
            ob = self.ob_engine.detect_ob(self.candles, micro)
            micro["ob"] = ob

            # 4. Forecast institucional
            forecast = self.forecast_engine.predict(self.candles, micro)

            # 5. Timing institucional
            timing = self.timing.evaluate(self.candles)

            # 6. Contexto institucional
            context = self.context.evaluate(self.candles)

            # 7. Señal institucional
            signal = self.signal.build_signal(
                self.tf, micro, context, timing, None, forecast
            )

            # ====================================================
            #   IMPRESIÓN DEL CHECKING
            # ====================================================
            print(f"\n--- VELA {i+1} ---")
            print(f"Open={c.open:.2f} High={c.high:.2f} Low={c.low:.2f} Close={c.close:.2f}")

            print("\n[ MICROSTRUCTURE ]")
            print(micro)

            print("\n[ OB ]")
            print(ob)

            print("\n[ FORECAST ]")
            print(forecast)

            print("\n[ TIMING ]")
            print(timing)

            print("\n[ CONTEXT ]")
            print(context)

            print("\n[ SIGNAL ]")
            print(signal)

            # ====================================================
            #   VALIDACIONES AUTOMÁTICAS
            # ====================================================
            if micro.get("fake_displacement") and signal:
                print("❌ ERROR: Señal generada con fake displacement")

            if micro.get("mitigation_light") and signal:
                print("❌ ERROR: Señal generada con mitigación")

            if signal and not ob:
                print("⚠️ ADVERTENCIA: Señal sin OB institucional")

            if signal:
                print("✔️ Señal válida detectada")

            time.sleep(0.1)


# ============================================================
#   EJECUCIÓN DIRECTA
# ============================================================
if __name__ == "__main__":
    checker = BiumoloChecking()
    checker.run(steps=80)
