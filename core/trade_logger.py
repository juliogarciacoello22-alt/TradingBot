import time
import json
from datetime import datetime


class TradeLogger:
    """
    SCALPING PRO — G EDITION
    Logger institucional v4:
    - Registra señales V4
    - Registra invalidaciones
    - Registra TP / BE / cierres
    - Guarda micro, contexto, timing, riesgo
    """

    def __init__(self, save_to_file=True, file_path="trade_log.jsonl", debug=False):
        self.save_to_file = save_to_file
        self.file_path = file_path
        self.memory_log = []
        self.debug = debug

    # ============================================================
    #   TIMESTAMP
    # ============================================================
    def _timestamp(self):
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # ============================================================
    #   GUARDAR EN ARCHIVO
    # ============================================================
    def _write_file(self, data):
        if not self.save_to_file:
            return
        try:
            with open(self.file_path, "a") as f:
                f.write(json.dumps(data) + "\n")
        except Exception as e:
            print(f"[LOGGER ERROR] No se pudo escribir archivo: {e}")

    # ============================================================
    #   REGISTRO BASE
    # ============================================================
    def _log(self, event_type, payload):
        entry = {
            "timestamp": self._timestamp(),
            "event": event_type,
            **payload
        }

        # memoria limitada
        self.memory_log.append(entry)
        if len(self.memory_log) > 2000:
            self.memory_log = self.memory_log[-1000:]

        self._write_file(entry)

        if self.debug:
            print(f"[LOGGER] {event_type.upper()} → {payload.get('reason', '')}")

    # ============================================================
    #   REGISTRAR SEÑAL (V4)
    # ============================================================
    def log_signal(self, signal):
        meta = signal.get("meta", {}) or {}

        self._log("signal", {
            "side": signal.get("side"),
            "mode": signal.get("mode"),
            "entry": signal.get("entry"),
            "stop": signal.get("stop"),
            "tp1": signal.get("tp1"),
            "tp2": signal.get("tp2"),
            "tp3": signal.get("tp3"),
            "score": signal.get("score"),

            # institucional
            "micro": meta.get("micro"),
            "context": meta.get("context"),
            "timing": meta.get("timing"),
            "risk": meta.get("risk"),

            "reason": "signal_generated"
        })

    # ============================================================
    #   REGISTRAR INVALIDACIÓN
    # ============================================================
    def log_invalidation(self, signal, reason):
        self._log("invalidation", {
            "side": signal.get("side"),
            "entry": signal.get("entry"),
            "stop": signal.get("stop"),
            "reason": reason
        })

    # ============================================================
    #   REGISTRAR BREAK-EVEN
    # ============================================================
    def log_break_even(self, signal, new_stop):
        self._log("break_even", {
            "side": signal.get("side"),
            "entry": signal.get("entry"),
            "old_stop": signal.get("stop"),
            "new_stop": new_stop,
            "reason": "SL movido a BE"
        })

    # ============================================================
    #   REGISTRAR TP
    # ============================================================
    def log_take_profit(self, signal, tp_level: int):
        self._log("take_profit", {
            "side": signal.get("side"),
            "entry": signal.get("entry"),
            "tp_hit": tp_level,
            "reason": f"TP{tp_level} alcanzado"
        })

    # ============================================================
    #   REGISTRAR CIERRE TOTAL
    # ============================================================
    def log_close(self, signal, reason):
        self._log("close", {
            "side": signal.get("side"),
            "entry": signal.get("entry"),
            "stop": signal.get("stop"),
            "reason": reason
        })
