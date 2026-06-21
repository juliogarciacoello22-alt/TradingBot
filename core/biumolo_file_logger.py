import os
import json
import datetime
from datetime import datetime as dt

# ============================================================
#   LOGGER SIMPLE (línea por línea)
# ============================================================
class FileLogger:

    def __init__(self, filename="biumolo_institucional.log"):
        self.filename = filename

    def write(self, text):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.filename, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")


_basic_logger = FileLogger()


def log_institucional_file_basic(candle, micro):
    """Write the compact candle and microstructure diagnostic log."""
    try:
        _basic_logger.write("===== VELA =====")
        _basic_logger.write(
            f"timestamp={candle.timestamp} O={candle.open} H={candle.high} "
            f"L={candle.low} C={candle.close}"
        )
        _basic_logger.write("===== MICRO =====")
        for key, value in micro.items():
            _basic_logger.write(f"{key}: {value}")
        _basic_logger.write("====================================")
    except Exception as exc:
        print("ERROR en log_institucional_file_basic:", exc)


# ============================================================
#   LOGGER EXTENDIDO (JSONL institucional)
# ============================================================
LOG_DIR = "logs_institucional"
os.makedirs(LOG_DIR, exist_ok=True)


def log_institucional_file_extended(candle, micro, intent_score, intent_reasons, pipeline_signal):
    """
    Log institucional EXTENDIDO:
    - vela 1m
    - microestructura completa
    - intent score
    - pipeline
    - reaction_ctx
    """

    try:
        # ----------------------------
        # Normalizar timestamp
        # ----------------------------
        ts = candle.timestamp
        if isinstance(ts, (int, float)):
            ts = dt.fromtimestamp(ts)
        elif isinstance(ts, str):
            ts = dt.fromisoformat(ts)

        filename = os.path.join(LOG_DIR, f"{ts.date()}_extended.jsonl")

        # ----------------------------
        # Reaction context
        # ----------------------------
        reaction_ctx = None
        if pipeline_signal:
            reaction_ctx = pipeline_signal.get("meta", {}).get("reaction_ctx")

        # ----------------------------
        # Registro completo
        # ----------------------------
        record = {
            "timestamp": ts.isoformat(),
            "candle": {
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "body": candle.body,
                "wick_up": candle.wick_up,
                "wick_down": candle.wick_down,
                "range": candle.range,
            },
            "micro": {
                "bos": micro.get("bos"),
                "choch": micro.get("choch"),
                "sweep": micro.get("sweep"),
                "sweep_price": micro.get("sweep_price"),
                "displacement": micro.get("displacement"),
                "fake_displacement": micro.get("fake_displacement"),
                "momentum": micro.get("momentum"),
                "absorption": micro.get("absorption"),
                "inducement": micro.get("inducement"),
                "mitigation_light": micro.get("mitigation_light"),
                "breaker": micro.get("breaker"),
                "volatility": micro.get("volatility"),
                "compression": micro.get("compression"),
                "expansion": micro.get("expansion"),
                "liquidity": micro.get("liquidity"),
            },
            "intent_score": intent_score,
            "intent_reasons": intent_reasons,
            "pipeline": pipeline_signal,
            "reaction_ctx": reaction_ctx,
        }

        # ----------------------------
        # Guardar en archivo JSONL
        # ----------------------------
        with open(filename, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    except Exception as e:
        print("ERROR en log_institucional_file_extended:", e)
