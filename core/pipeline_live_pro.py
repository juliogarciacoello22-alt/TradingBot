import asyncio
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
from core import audit_session_logger
from core.ob_engine import OBEngine
from core.dedup_engine import DeduplicationEngine
from core.biumolo_config import BASIC_LOG_ONLY


def safe_print(*args):
    text = " ".join(str(arg) for arg in args)
    print(text.encode("ascii", errors="replace").decode("ascii"))


ACTIVATION_MINUTES = 0
_AUDIT_REASON_KEYS = (
    "mitigation_light_reason",
    "mitigation_overlap_reason",
    "mitigation_light_v2_reason",
    "mitigation_contamination_reason",
)
_AUDIT_REQUIRED_SNAPSHOT_FIELDS = (
    ("snapshot.microstructure", lambda snapshot: snapshot.get("microstructure")),
    (
        "snapshot.micro.ob",
        lambda snapshot: (snapshot.get("microstructure") or {}).get("ob")
        if isinstance(snapshot.get("microstructure"), dict)
        else None,
    ),
    ("snapshot.timing", lambda snapshot: snapshot.get("timing")),
    ("snapshot.delta", lambda snapshot: snapshot.get("delta")),
    ("snapshot.last_candle", lambda snapshot: snapshot.get("last_candle")),
    ("snapshot.tf", lambda snapshot: snapshot.get("tf")),
    ("snapshot.context", lambda snapshot: snapshot.get("context")),
    ("snapshot.forecast", lambda snapshot: snapshot.get("forecast")),
    ("snapshot.price", lambda snapshot: snapshot.get("price")),
)


def _audit_jsonable(value, depth=0):
    if depth > 6:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _audit_jsonable(item, depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_audit_jsonable(item, depth + 1) for item in value]
    if hasattr(value, "__dict__"):
        return {
            str(key): _audit_jsonable(item, depth + 1)
            for key, item in vars(value).items()
            if not str(key).startswith("_")
        }
    return str(value)


def _audit_field_present(value):
    return value is not None


def _audit_required_snapshot_fields(snapshot):
    return [(name, getter(snapshot)) for name, getter in _AUDIT_REQUIRED_SNAPSHOT_FIELDS]


def _audit_missing_snapshot_fields(snapshot):
    missing = [name for name, value in _audit_required_snapshot_fields(snapshot) if not _audit_field_present(value)]
    if not snapshot.get("decision_id") and not snapshot.get("timestamp"):
        missing.append("decision_id_or_timestamp")
    return missing


def _full_path_microstructure_snapshot(micro):
    payload = _audit_jsonable(micro)
    if not isinstance(payload, dict):
        return payload
    source = micro if isinstance(micro, dict) else {}
    for key in _AUDIT_REASON_KEYS:
        payload[key] = _audit_jsonable(source.get(key))
    return payload


def _snapshot_timestamp(raw, candle):
    timestamp = raw.get("timestamp") if isinstance(raw, dict) else None
    if timestamp is None:
        timestamp = getattr(candle, "timestamp", None)
    return timestamp


def _snapshot_last_candle(tf, candle):
    if isinstance(tf, dict) and tf.get("1m"):
        return tf["1m"][-1]
    return candle


def _signal_engine_stage_snapshot(signal_engine, signal):
    return {
        "signal_engine": {
            "last_valid_entry_reason": getattr(signal_engine, "last_valid_entry_reason", None),
            "last_build_signal_reason": getattr(signal_engine, "last_build_signal_reason", None),
            "last_valid_entry_shadow": _audit_jsonable(getattr(signal_engine, "last_valid_entry_shadow", None)),
            "signal_is_none": signal is None,
        }
    }


def _build_full_path_snapshot(
    *,
    session_id,
    raw,
    candle,
    tf,
    micro_for_valid_entry,
    timing,
    delta,
    context,
    forecast,
    signal_engine,
    signal,
):
    timestamp = _snapshot_timestamp(raw, candle)
    decision_id = f"{session_id}|{timestamp}" if timestamp is not None else None
    last_candle = _snapshot_last_candle(tf, candle)
    snapshot = {
        "decision_id": decision_id,
        "timestamp": timestamp,
        "microstructure": _full_path_microstructure_snapshot(micro_for_valid_entry),
        "timing": _audit_jsonable(timing),
        "delta": _audit_jsonable(delta),
        "last_candle": _audit_jsonable(last_candle),
        "tf": _audit_jsonable(tf),
        "context": _audit_jsonable(context),
        "forecast": _audit_jsonable(forecast),
        "price": getattr(last_candle, "close", None),
        "stage_outputs": _signal_engine_stage_snapshot(signal_engine, signal),
    }
    snapshot["missing_fields"] = _audit_missing_snapshot_fields(snapshot)
    return snapshot


def _emit_full_path_snapshot_audit(
    *,
    raw,
    candle,
    tf,
    micro_for_valid_entry,
    timing,
    delta,
    context,
    forecast,
    signal_engine,
    signal,
):
    try:
        snapshot = _build_full_path_snapshot(
            session_id=audit_session_logger.get_session_id(),
            raw=raw,
            candle=candle,
            tf=tf,
            micro_for_valid_entry=micro_for_valid_entry,
            timing=timing,
            delta=delta,
            context=context,
            forecast=forecast,
            signal_engine=signal_engine,
            signal=signal,
        )
        audit_session_logger.append_jsonl(
            "signal_engine_full_path_snapshots.jsonl",
            {
                "event": "signal_engine_v4_full_path_snapshot",
                "snapshot": snapshot,
            },
        )
    except Exception as exc:
        _decision_log(
            "full_path_snapshot_audit",
            False,
            "snapshot_audit_failed",
            repr(exc),
        )


def _decision_log(stage, allowed, reason, detail):
    safe_print(
        ">> PIPELINE DECISION stage={stage} allowed={allowed} reason={reason} detail={detail}".format(
            stage=stage,
            allowed=allowed,
            reason=reason,
            detail=detail,
        )
    )

class PipelineLivePRO:
    """
    PipelineLive PRO â€” ÃšNICO pipeline productivo
    --------------------------------------------
    - Feed 1m â†’ Timeframes
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
    - EnvÃ­o a Telegram / NinjaTrader
    """

    def __init__(self, api, is_live=True):
        self.api = api
        self.is_live = is_live  # ðŸ”’ bloqueo institucional de envÃ­o
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
    # LOG DE SEÃ‘ALES
    # ------------------------------------------------------------
    def _log_signal(self, final_signal):
        os.makedirs("logs", exist_ok=True)
        path = os.path.join("logs", "signals.log")
        with open(path, "a") as f:
            f.write(json.dumps(final_signal) + "\n")

    # ------------------------------------------------------------
    # PROCESO PRINCIPAL
    # ------------------------------------------------------------
    def _dispatch_signal(self, signal):
        coro = self.api.send_signal(signal)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        task = loop.create_task(coro)

        def _done_callback(done_task):
            try:
                exc = done_task.exception()
            except Exception as err:
                safe_print(f"SIGNAL DISPATCH CALLBACK ERROR: {err}")
                return
            if exc:
                safe_print(f"SIGNAL DISPATCH ERROR: {exc}")

        task.add_done_callback(_done_callback)
        return task

    def process(self, raw):
        try:
            if not BASIC_LOG_ONLY:
                safe_print("PIPELINE LIVE PRO RECEIVED:", raw)

            # 0) PING
            if raw.get("ping") is True:
                return None

            # 1) SEÃ‘AL MANUAL
            if "side" in raw and "entry" in raw and "stop" in raw:
                safe_print("MANUAL SIGNAL RECEIVED:", raw)

                valid, reason = execution_engine.validate(
                    tf={"1m": [], "5m": [], "30m": []},
                    micro={},
                    signal=raw,
                    context={},
                    timing={},
                    delta={}
                )

                if not valid:
                    safe_print("MANUAL SIGNAL CANCELLED -", reason)
                    return None

                # ðŸ”’ bloqueo por is_live
                if self.is_live:
                    self._dispatch_signal(raw)
                    safe_print("MANUAL SIGNAL SENT")
                else:
                    safe_print("HISTORICAL MODE - manual signal not sent")

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

            # 5) REQUISITOS MÃNIMOS
            if len(tf["1m"]) < 1 or len(tf["5m"]) < 3 or len(tf["30m"]) < 1:
                return None

            candle = tf["1m"][-1]

            # 6) GESTIÃ“N DE SALIDA
            if self.exit_engine.has_open_trade():
                trade_closed = self.exit_engine.check_exit(candle.close)
                if trade_closed:
                    log_trade(trade_closed)
                    safe_print("TRADE CLOSED:", trade_closed)

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
                delta=delta_value,   # numÃ©rico
                forecast=forecast
            )
            _emit_full_path_snapshot_audit(
                raw=raw,
                candle=candle,
                tf=tf,
                micro_for_valid_entry=micro,
                timing=timing,
                delta=delta_value,
                context=context,
                forecast=forecast,
                signal_engine=self.signal_engine,
                signal=signal,
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
                    safe_print("SIGNAL CANCELLED BY RISKENGINE -", risk)
                    signal = None

            # 15) FILTRO POR TIMING
            if signal:
                if isinstance(timing, dict) and not timing.get("valid", True):
                    safe_print("SIGNAL CANCELLED BY TIMINGENGINE -", timing.get("reason"))
                    signal = None

            # 16) VALIDACIÃ“N FINAL â€” EXECUTION ENGINE PRO
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
                    safe_print("SIGNAL REJECTED BY EXECUTIONENGINE -", reason)

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

            # 19) LOG + DEDUP + ENVÃO + ABRIR TRADE
            if final_signal:

                if self.dedup.is_duplicate(final_signal):
                    safe_print("SIGNAL DUPLICATE - discarded")
                else:
                    safe_print("SIGNAL NEW - processed")
                    self._log_signal(final_signal)

                    if self.is_live:
                        self._dispatch_signal(final_signal)
                        self.exit_engine.open_from_signal(final_signal)
                        safe_print("INSTITUTIONAL SIGNAL SENT TO TELEGRAM / NINJATRADER")
                    else:
                        safe_print("HISTORICAL MODE - signal not sent, logged only")

            # actualizar prev_delta
            self.api.prev_delta = delta_value

            _decision_log(
                "process",
                final_signal is not None,
                "ok" if final_signal is not None else "no_final_signal",
                "side={side} mode={mode}".format(
                    side=None if final_signal is None else final_signal.get("side"),
                    mode=None if final_signal is None else final_signal.get("mode"),
                ),
            )
            return final_signal

        except Exception as e:
            safe_print("ERROR IN PIPELINE LIVE PRO:", e)
            traceback.print_exc()
            _decision_log("process", False, "exception", repr(e))
            return None



