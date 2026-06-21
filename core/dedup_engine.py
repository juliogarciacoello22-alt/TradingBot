# core/dedup_engine.py

import hashlib
import json
import time


class DeduplicationEngine:
    """
    DeduplicationEngine PRO — BIUMOLO INSTITUCIONAL
    ------------------------------------------------
    Evita señales duplicadas:
    - misma estructura
    - mismo OB
    - mismo entry/stop/tp
    - misma microestructura
    - misma dirección
    """

    def __init__(self):
        self.last_signature = None
        self.last_timestamp = 0
        self.cooldown_ms = 15000  # 15 segundos institucional

    # ============================================================
    #   GENERAR FIRMA INSTITUCIONAL
    # ============================================================
    def _make_signature(self, signal):
        """
        Crea una firma HASH estable basada en los campos institucionales.
        """
        try:
            base = {
                "side": signal.get("side"),
                "mode": signal.get("mode"),
                "entry": round(signal.get("entry", 0), 4),
                "stop": round(signal.get("stop", 0), 4),
                "tp1": round(signal.get("tp1", 0), 4),
                "tp2": round(signal.get("tp2", 0), 4),
                "tp3": round(signal.get("tp3", 0), 4),
                "ob": signal.get("ob"),
                "reason": signal.get("reason"),
            }

            raw = json.dumps(base, sort_keys=True)
            return hashlib.sha256(raw.encode()).hexdigest()

        except Exception as e:
            print("ERROR EN DEDUP (signature):", e)
            return None

    # ============================================================
    #   VALIDAR SI ES DUPLICADA
    # ============================================================
    def is_duplicate(self, signal):
        """
        Devuelve True si la señal es duplicada.
        """
        try:
            sig = self._make_signature(signal)
            if sig is None:
                return False

            now = int(time.time() * 1000)

            # cooldown institucional (evita spam)
            if now - self.last_timestamp < self.cooldown_ms:
                if sig == self.last_signature:
                    return True

            # actualizar firma
            self.last_signature = sig
            self.last_timestamp = now
            return False

        except Exception as e:
            print("ERROR EN DEDUP (is_duplicate):", e)
            return False
