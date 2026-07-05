from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from core.api import API
import json
import traceback

from core.biumolo_logger import log
from core.biumolo_config import (
    SHOW_STARTUP_STATUS,
    BASIC_LOG_ONLY,
    MAX_LIVE_BAR_DRIFT_SECONDS,
)
from core.execution_engine_pro import execution_engine
from core.live_timestamp_validator import validate_bar_timestamp
from core.pipeline_live_pro import PipelineLivePRO
from core.runtime_guard import sync_api_runtime_mode

app = FastAPI()
api = API()

# Activar pipeline PRO unificado
api.pipeline = PipelineLivePRO(api)

# Live/historical flag bound to RUN_MODE.
sync_api_runtime_mode(api)


# ============================================================
#   STATUS
# ============================================================
if SHOW_STARTUP_STATUS:
    print("=====================================")
    print("         BIUMOLO SERVER ONLINE       ")
    print("=====================================")


# ============================================================
#   ENDPOINT: ENVIAR SEÑAL MANUAL
# ============================================================
@app.post("/send_signal")
async def send_signal(signal: dict):
    sync_api_runtime_mode(api)

    print(">>> Senal manual recibida:", signal)

    valid, reason = execution_engine.validate(
        tf={"1m": [], "5m": [], "30m": []},
        micro={},
        signal=signal,
        context={},
        timing={},
        delta={}
    )

    if not valid:
        print(">>> SENAL MANUAL CANCELADA -", reason)
        return {"status": "rejected", "reason": reason}

    result = await api.send_signal(signal)
    if isinstance(result, dict) and not result.get("allowed", True):
        return {
            "status": "blocked",
            "reason": result.get("reason"),
            "run_mode": result.get("run_mode"),
            "account": result.get("account"),
            "EnableTrading": result.get("enable_trading"),
        }
    return {"status": "ok", "sent": signal}


# ============================================================
#   WEBSOCKET /ws (interno)
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(">> Cliente conectado al WebSocket /ws")

    try:
        while True:
            data = await websocket.receive_text()
            parsed = json.loads(data)
            await websocket.send_text("OK")
    except WebSocketDisconnect:
        print(">> Cliente desconectado de /ws")


# ============================================================
#   WEBSOCKET /stream (NinjaTrader → FastAPI)
# ============================================================
@app.websocket("/stream")
async def stream_socket(websocket: WebSocket):

    await websocket.accept()

    if api.ws is not None:
        print(">> Advertencia: conexion previa detectada. Reemplazando WebSocket institucional.")
    api.ws = websocket

    print(">> NinjaTrader conectado via /stream")

    try:
        while True:
            data = await websocket.receive_text()
            if not BASIC_LOG_ONLY:
                print("NinjaTrader envio:", data)

            # Parsear JSON
            try:
                msg = json.loads(data)
            except Exception as e:
                print("ERROR parseando JSON:", e)
                continue

            # PING
            if msg.get("ping") is True:
                if not BASIC_LOG_ONLY:
                    print("PING recibido -> ignorado")
                continue

            # Señal manual institucional
            is_manual_signal = all(k in msg for k in ("side", "entry", "stop"))
            if is_manual_signal:
                print(">> SENAL MANUAL RECIBIDA:", msg)

                valid, reason = execution_engine.validate(
                    tf={"1m": [], "5m": [], "30m": []},
                    micro={},
                    signal=msg,
                    context={},
                    timing={},
                    delta={}
                )

                if not valid:
                    print(">> SENAL MANUAL CANCELADA -", reason)
                    continue

                await api.send_signal(msg)
                continue

            # ============================================================
            #   VELAS REALES → FEED + PIPELINE LIVE PRO
            # ============================================================
            try:
                if not validate_bar_timestamp(
                    msg.get("timestamp"),
                    live_mode=getattr(api, "is_live", True),
                    max_drift_seconds=MAX_LIVE_BAR_DRIFT_SECONDS,
                ):
                    continue

                accepted = api.feed.push(msg)

                if not accepted:
                    print(">> Vela rechazada por Feed -> pipeline NO ejecutado")
                    continue

                # FIX: evitar señales en histórico
                if not getattr(api, "is_live", True):
                    api.pipeline.process(msg)  # procesa pero NO envía señales
                    continue

                api.pipeline.process(msg)

            except Exception as e:
                print("ERROR en PIPELINE LIVE PRO:", e)
                traceback.print_exc()

    except WebSocketDisconnect:
        print(">> NinjaTrader desconectado de /stream")

        if api.ws == websocket:
            api.ws = None
