import json
import os
import asyncio
from core.feed import Feed
from core.telegram_bot import TelegramBot


class API:
    def __init__(self):
        self.last_signal = None
        self.feed = Feed()

        # Telegram Bot
        self.telegram = TelegramBot(
            os.getenv("TELEGRAM_TOKEN"),
            os.getenv("TELEGRAM_CHAT_ID")
        )

        # WebSocket de NinjaTrader (inyectado desde server.py)
        self.ws = None

        # Timeframes institucionales
        self.timeframes = {
            "1m": [],
            "5m": [],
            "30m": [],
            "4h": []
        }

    # ============================================================
    #   FORMATO INSTITUCIONAL PARA TELEGRAM (CORREGIDO V4)
    # ============================================================
    def format_biumolo_signal(self, signal):
        # side BUY/SELL → direction long/short
        side = signal.get("side")
        direction = "long" if side == "BUY" else "short" if side == "SELL" else "neutral"

        entry = signal.get("entry", "N/A")
        stop  = signal.get("stop", "N/A")
        tp1   = signal.get("tp1", "N/A")
        tp2   = signal.get("tp2", "N/A")
        tp3   = signal.get("tp3", "N/A")

        meta = signal.get("meta", {}) or {}
        micro   = meta.get("micro", {})
        context = meta.get("context", {})
        timing  = meta.get("timing", {})
        risk    = meta.get("risk", {})

        emoji = "🟩 BUY" if side == "BUY" else "🟥 SELL" if side == "SELL" else "⚪️"

        msg = f"""
<b>{emoji} — BIUMOLO SIGNAL</b>
━━━━━━━━━━━━━━━━━━

<b>🎯 Setup</b>
• <b>Entry:</b> {entry}
• <b>Stop:</b> {stop}
• <b>TP1:</b> {tp1}
• <b>TP2:</b> {tp2}
• <b>TP3:</b> {tp3}

<b>📉 Microstructure</b>
• Sweep: {micro.get("sweep")}
• Displacement: {micro.get("displacement")}
• Momentum: {micro.get("momentum")}
• Absorption: {micro.get("absorption")}
• Inducement: {micro.get("inducement")}
• Breaker: {micro.get("breaker")}
• FVG: {micro.get("fvg")}
• Premium: {micro.get("premium")}
• Discount: {micro.get("discount")}

<b>🧠 Contexto</b>
• Intent 5m: {context.get("intent_5m")}
• Trend 4h: {context.get("trend_4h")}
• BOS 5m: {context.get("bos_5m")}
• CHOCH 5m: {context.get("choch_5m")}

<b>⏱ Timing</b>
• Session: {timing.get("session")}
• Volatility: {timing.get("volatility")}
• Valid: {timing.get("valid")}

<b>⚠️ Risk Engine</b>
• Valid: {risk.get("valid")}
• Score: {risk.get("score")}
• Reason: {risk.get("reason")}

━━━━━━━━━━━━━━━━━━
<b>BIUMOLO — Institutional Engine</b>
"""
        return msg.strip()

    # ============================================================
    #   ENVÍO ASÍNCRONO (NinjaTrader + Telegram)
    # ============================================================
    async def _send_to_ninjatrader(self, signal):
        if not self.ws:
            print(">>> NinjaTrader no conectado — señal NO enviada")
            return

        try:
            await self.ws.send_text(json.dumps(signal))
            print(">>> Señal enviada a NinjaTrader vía WebSocket")
        except Exception as e:
            print("ERROR enviando señal a NinjaTrader:", e)

    async def _send_to_telegram(self, signal):
        try:
            msg = self.format_biumolo_signal(signal)
            await asyncio.to_thread(self.telegram.send, msg)
            print(">>> Señal enviada a Telegram")
        except Exception as e:
            print("ERROR enviando señal a Telegram:", e)

    # ============================================================
    #   API PÚBLICA — ENVÍO ASÍNCRONO REAL (CORREGIDO)
    # ============================================================
    async def send_signal(self, signal):
        self.last_signal = signal
        print(">>> Señal recibida:", signal)

        # Envío paralelo: NinjaTrader + Telegram
        await asyncio.gather(
            self._send_to_ninjatrader(signal),
            self._send_to_telegram(signal)
        )

    # ============================================================
    #   OBTENER ÚLTIMA SEÑAL
    # ============================================================
    def get_last_signal(self):
        return self.last_signal
