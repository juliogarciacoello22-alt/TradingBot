# core/exit_engine.py

from dataclasses import dataclass
from typing import Optional, Dict, Any
import time

@dataclass
class OpenTrade:
    side: str
    entry: float
    stop: float
    tp1: Optional[float]
    tp2: Optional[float]
    tp3: Optional[float]
    timestamp_entry: int
    meta: Dict[str, Any]

class ExitEngine:
    def __init__(self):
        self.current_trade: Optional[OpenTrade] = None

    def open_from_signal(self, signal: dict) -> None:
        """
        Abre un trade interno a partir de una señal institucional.
        No loguea nada, solo guarda el estado.
        """
        if self.current_trade is not None:
            return

        # normalizar BUY/SELL
        side = signal.get("side", "").lower()
        entry = signal.get("entry")
        stop = signal.get("stop")

        # ============================
        #   CORRECCIÓN DE TPs
        # ============================
        tp1 = signal.get("tp1")
        tp2 = signal.get("tp2")
        tp3 = signal.get("tp3")

        self.current_trade = OpenTrade(
            side=side,
            entry=entry,
            stop=stop,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            timestamp_entry=int(time.time()),
            meta=signal.get("meta", {})
        )

    def check_exit(self, price: float) -> Optional[dict]:
        """
        Revisa si el trade abierto debe cerrarse por TP/SL.
        Devuelve un dict de trade cerrado o None si sigue abierto.
        """
        if self.current_trade is None:
            return None

        t = self.current_trade
        side = t.side

        hit = None
        exit_price = None

        if side == "buy":
            # STOP
            if price <= t.stop:
                hit = "SL"
                exit_price = t.stop
            # TP3 > TP2 > TP1
            elif t.tp3 is not None and price >= t.tp3:
                hit = "TP3"
                exit_price = t.tp3
            elif t.tp2 is not None and price >= t.tp2:
                hit = "TP2"
                exit_price = t.tp2
            elif t.tp1 is not None and price >= t.tp1:
                hit = "TP1"
                exit_price = t.tp1

        elif side == "sell":
            # STOP
            if price >= t.stop:
                hit = "SL"
                exit_price = t.stop
            # TP3 < TP2 < TP1
            elif t.tp3 is not None and price <= t.tp3:
                hit = "TP3"
                exit_price = t.tp3
            elif t.tp2 is not None and price <= t.tp2:
                hit = "TP2"
                exit_price = t.tp2
            elif t.tp1 is not None and price <= t.tp1:
                hit = "TP1"
                exit_price = t.tp1

        if hit is None:
            return None

        # cálculo de R
        risk_per_point = abs(t.entry - t.stop)
        if risk_per_point == 0:
            result_R = 0.0
        else:
            result_R = (exit_price - t.entry) / risk_per_point
            if side == "sell":
                result_R = -result_R

        trade_closed = {
            "timestamp_entry": t.timestamp_entry,
            "timestamp_exit": int(time.time()),
            "side": t.side,
            "entry": t.entry,
            "stop": t.stop,
            "exit": exit_price,
            "result_R": result_R,
            "tp_hit": hit,
            "meta": t.meta,
        }

        # cerrar estado interno
        self.current_trade = None
        return trade_closed

    def has_open_trade(self) -> bool:
        return self.current_trade is not None
