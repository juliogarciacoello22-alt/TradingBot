from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time
from pathlib import Path
from statistics import mean

TICK = 0.25


def tick(value: float) -> float:
    return math.floor(value / TICK + 0.5) * TICK


@dataclass
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    atr: float | None = None
    vwap: float | None = None
    sigma: float | None = None

    @property
    def range(self):
        return self.high - self.low

    @property
    def body_ratio(self):
        return abs(self.close - self.open) / self.range if self.range else 0.0


@dataclass
class Level:
    ident: str
    kind: str
    lower: float
    upper: float
    created: datetime
    tests: int = 0
    state: str = "fresco"
    armed: bool = False
    active: bool = True
    inside_count: int = 0
    dynamic: bool = False

    def update_state(self):
        self.state = ("fresco" if self.tests == 0 else "valido" if self.tests == 1
                      else "debilitado" if self.tests == 2 else "invalidado")
        if self.tests >= 3:
            self.active = False


@dataclass
class Setup:
    level_id: str
    level_kind: str
    lower: float
    upper: float
    side: str
    touched_index: int
    event_index: int
    event_extreme: float
    event_type: str
    above_count: int = 0
    below_count: int = 0
    recovered: bool = False


@dataclass
class Trade:
    entry_day: str
    ts: datetime
    side: str
    level: str
    event: str
    entry: float
    stop: float
    risk: float
    tp1: float
    atr: float
    volume: float
    volume20: float
    confirmations: list[str]
    result: str | None = None
    result_r: float | None = None
    exit_ts: datetime | None = None


def cme_day(ts: datetime):
    return (ts + timedelta(days=1)).date() if ts.time() >= time(17) else ts.date()


def read_bars(path: Path):
    bars = []
    with path.open(encoding="utf-8-sig") as fh:
        for line in fh:
            if not line.strip():
                continue
            parts = line.strip().split(";")
            ts = datetime.strptime(parts[0], "%Y%m%d %H%M%S")
            o, h, lo, c = (tick(float(x)) for x in parts[1:5])
            bars.append(Bar(ts, o, h, lo, c, float(parts[5])))
    bars.sort(key=lambda b: b.ts)
    return bars


def update_aggregate(state, b: Bar, minutes: int):
    key = b.ts.replace(minute=(b.ts.minute // minutes) * minutes, second=0)
    current = state.get("current")
    if current is None:
        state["key"] = key
        state["current"] = Bar(key, b.open, b.high, b.low, b.close, b.volume)
        return False
    if key == state["key"]:
        current.high = max(current.high, b.high)
        current.low = min(current.low, b.low)
        current.close = b.close
        current.volume += b.volume
        return False
    state["series"].append(current)
    state["key"] = key
    state["current"] = Bar(key, b.open, b.high, b.low, b.close, b.volume)
    return True


def add_level(levels, kind, lower, upper, ts, suffix=""):
    lower, upper = tick(min(lower, upper)), tick(max(lower, upper))
    ident = f"{kind}:{ts:%Y%m%d%H%M}:{lower:.2f}:{upper:.2f}:{suffix}"
    if ident not in levels:
        levels[ident] = Level(ident, kind, lower, upper, ts)
    return levels[ident]


def pivot_levels(levels, series, minutes):
    if len(series) < 5:
        return
    i = len(series) - 3
    p = series[i]
    neighbors = series[i-2:i] + series[i+1:i+3]
    confirmed = series[-1].ts + timedelta(minutes=minutes)
    if p.high > max(x.high for x in neighbors):
        add_level(levels, f"swing_high_{minutes}m", p.high-TICK, p.high+TICK, confirmed)
    if p.low < min(x.low for x in neighbors):
        add_level(levels, f"swing_low_{minutes}m", p.low-TICK, p.low+TICK, confirmed)


def touched(b, lv):
    return b.high >= lv.lower-TICK and b.low <= lv.upper+TICK


def rejection(b, lv, side):
    if not b.range or not (lv.lower <= b.close <= lv.upper):
        return False
    if side == "BUY":
        return min(b.open, b.close)-b.low >= 0.40*b.range
    return b.high-max(b.open, b.close) >= 0.40*b.range


def sweep(b, lv, side):
    if side == "BUY":
        return b.low < lv.lower-TICK and b.close >= lv.lower
    return b.high > lv.upper+TICK and b.close <= lv.upper


def micro_confirmation(highs, lows, side):
    if len(highs) < 2 or len(lows) < 2:
        return False
    return (highs[-1] > highs[-2] and lows[-1] > lows[-2]) if side == "BUY" else (
        highs[-1] < highs[-2] and lows[-1] < lows[-2])


def run(bars):
    levels: dict[str, Level] = {}
    setups: dict[tuple[str, str], Setup] = {}
    trades: list[Trade] = []
    rejections = defaultdict(Counter)
    date_strings = sorted({b.ts.strftime("%Y%m%d") for b in bars})
    day_signal_count = Counter()
    last_signal = {}
    active_trade = None
    current_cme, prior_range = None, None
    session_high = session_low = None
    op_date = None
    last_op_high_id = last_op_low_id = None
    published_op_high = published_op_low = None
    tr_seed, atr = [], None
    prev_close = None
    session_pv = session_v = session_p2v = 0.0
    volumes = deque(maxlen=20)
    tf5 = {"series": [], "current": None}
    tf15 = {"series": [], "current": None}
    dynamic = {}
    micro_highs, micro_lows = [], []

    for idx, b in enumerate(bars):
        # Wilder ATR, continuous and causal.
        tr = b.high-b.low if prev_close is None else max(b.high-b.low, abs(b.high-prev_close), abs(b.low-prev_close))
        if atr is None:
            tr_seed.append(tr)
            if len(tr_seed) == 14:
                atr = mean(tr_seed)
        else:
            atr += (tr-atr)/14
        b.atr = atr
        prev_close = b.close

        cd = cme_day(b.ts)
        if current_cme != cd:
            if current_cme is not None:
                prior_range = (cme_hi, cme_lo)
            current_cme, cme_hi, cme_lo = cd, b.high, b.low
            session_pv = session_v = session_p2v = 0.0
            add_level(levels, "cme_open", b.open-TICK, b.open+TICK, b.ts)
            if prior_range:
                add_level(levels, "prior_high", prior_range[0]-TICK, prior_range[0]+TICK, b.ts)
                add_level(levels, "prior_low", prior_range[1]-TICK, prior_range[1]+TICK, b.ts)
        else:
            cme_hi, cme_lo = max(cme_hi, b.high), min(cme_lo, b.low)

        p = (b.high+b.low+b.close)/3
        session_pv += p*b.volume
        session_p2v += p*p*b.volume
        session_v += b.volume
        b.vwap = session_pv/session_v if session_v else p
        variance = max(0.0, session_p2v/session_v-b.vwap*b.vwap) if session_v else 0.0
        b.sigma = math.sqrt(variance)
        for kind, price in (("vwap", b.vwap), ("vwap_plus1", b.vwap+b.sigma),
                            ("vwap_minus1", b.vwap-b.sigma), ("vwap_plus2", b.vwap+2*b.sigma),
                            ("vwap_minus2", b.vwap-2*b.sigma)):
            if kind not in dynamic:
                dynamic[kind] = Level(f"dynamic:{kind}", kind, tick(price)-TICK, tick(price)+TICK, b.ts, dynamic=True)
            else:
                dynamic[kind].lower, dynamic[kind].upper = tick(price)-TICK, tick(price)+TICK

        day = b.ts.date()
        if op_date != day:
            op_date, session_high, session_low = day, None, None
        if time(6,30) <= b.ts.time() <= time(16):
            # Publish levels from extrema known before this candle.
            if session_high is not None and session_high != published_op_high:
                if last_op_high_id in levels:
                    levels[last_op_high_id].active = False
                lv = add_level(levels, "operational_high", session_high-TICK, session_high+TICK, b.ts)
                last_op_high_id = lv.ident
                published_op_high = session_high
            if session_low is not None and session_low != published_op_low:
                if last_op_low_id in levels:
                    levels[last_op_low_id].active = False
                lv = add_level(levels, "operational_low", session_low-TICK, session_low+TICK, b.ts)
                last_op_low_id = lv.ident
                published_op_low = session_low
            session_high = b.high if session_high is None else max(session_high, b.high)
            session_low = b.low if session_low is None else min(session_low, b.low)

        # Resolve an existing trade before evaluating close-based signals.
        was_open = active_trade is not None
        if active_trade:
            t = active_trade
            stop_hit = b.low <= t.stop if t.side == "BUY" else b.high >= t.stop
            tp_hit = b.high >= t.tp1 if t.side == "BUY" else b.low <= t.tp1
            if stop_hit or tp_hit:
                t.result = "STOP" if stop_hit else "TP1"
                exit_price = t.stop if stop_hit else t.tp1
                t.result_r = ((exit_price-t.entry)/t.risk if t.side == "BUY" else (t.entry-exit_price)/t.risk)
                t.exit_ts = b.ts
                active_trade = None

        if update_aggregate(tf5, b, 5):
            pivot_levels(levels, tf5["series"], 5)
        if update_aggregate(tf15, b, 15):
            pivot_levels(levels, tf15["series"], 15)
        # Confirm the 1m pivot at i only after i+2 has closed.
        if idx >= 4:
            i = idx-2
            neighbors = bars[i-2:i] + bars[i+1:i+3]
            if bars[i].high > max(x.high for x in neighbors):
                micro_highs.append(bars[i].high)
            if bars[i].low < min(x.low for x in neighbors):
                micro_lows.append(bars[i].low)

        # Causal imbalance and OB creation after their confirming bars close.
        if b.atr and b.range >= 1.5*b.atr and b.body_ratio >= .60:
            kind = "imbalance_buy" if b.close > b.open else "imbalance_sell"
            add_level(levels, kind, b.open, b.close, b.ts)
        if idx >= 2:
            ob, j, j1 = bars[idx-2], bars[idx-1], b
            if ob.close < ob.open and j.close > ob.high and j1.close > j.high:
                add_level(levels, "ob_buy", ob.open, ob.high, b.ts)
            if ob.close > ob.open and j.close < ob.low and j1.close < j.low:
                add_level(levels, "ob_sell", ob.low, ob.open, b.ts)

        # Two closes inside invalidate imbalance/OB zones.
        for lv in levels.values():
            if not lv.active or lv.created > b.ts:
                continue
            if lv.kind.startswith(("imbalance", "ob_")):
                lv.inside_count = lv.inside_count+1 if lv.lower <= b.close <= lv.upper else 0
                if lv.inside_count >= 2:
                    lv.active, lv.state = False, "invalidado"

        # Inactive levels can no longer participate in setups or RR checks.
        for ident in [ident for ident, lv in levels.items() if not lv.active]:
            levels.pop(ident, None)

        candidates = [x for x in levels.values() if x.active and x.created <= b.ts] + list(dynamic.values())
        if b.atr:
            for lv in candidates:
                distance = 0 if touched(b, lv) else min(abs(b.low-lv.upper), abs(b.high-lv.lower))
                if distance >= b.atr:
                    lv.armed = True
                if lv.armed and touched(b, lv):
                    lv.tests += 1
                    lv.armed = False
                    lv.update_state()

        # Advance or discard existing setups.
        ready = []
        for key, s in list(setups.items()):
            lv = levels.get(s.level_id) or dynamic.get(s.level_kind)
            if idx-s.touched_index >= 10 or lv is None or not lv.active:
                rejections[b.ts.strftime("%Y%m%d")]["setup_caducado_o_nivel_invalidado"] += 1
                del setups[key]
                continue
            if s.side == "BUY":
                s.below_count = s.below_count+1 if b.close < s.lower else 0
                if s.below_count >= 2:
                    rejections[b.ts.strftime("%Y%m%d")]["aceptacion_contraria"] += 1
                    del setups[key]; continue
                if b.close > s.upper:
                    s.recovered = True
                    s.above_count += 1
                else:
                    s.above_count = 0
            else:
                s.above_count = s.above_count+1 if b.close > s.upper else 0
                if s.above_count >= 2:
                    rejections[b.ts.strftime("%Y%m%d")]["aceptacion_contraria"] += 1
                    del setups[key]; continue
                if b.close < s.lower:
                    s.recovered = True
                    s.below_count += 1
                else:
                    s.below_count = 0
            accepted = s.above_count >= 2 if s.side == "BUY" else s.below_count >= 2
            if s.recovered and accepted:
                ready.append(s)

        # Start setups on a sweep/rejection. Same bar may satisfy touch and event.
        for lv in candidates:
            if not lv.active or lv.state not in ("fresco", "valido") or not touched(b, lv):
                continue
            for side in ("BUY", "SELL"):
                key = (lv.ident, side)
                if key in setups:
                    continue
                is_sweep, is_reject = sweep(b, lv, side), rejection(b, lv, side)
                if is_sweep or is_reject:
                    extreme = b.low if side == "BUY" else b.high
                    setups[key] = Setup(lv.ident, lv.kind, lv.lower, lv.upper, side, idx, idx,
                                        extreme, "barrida" if is_sweep else "rechazo")

        if ready:
            ds = b.ts.strftime("%Y%m%d")
            in_window = time(8,30) <= b.ts.time() <= time(11)
            if not in_window:
                rejections[ds]["fuera_horario"] += len(ready)
            elif was_open or active_trade:
                rejections[ds]["operacion_activa"] += len(ready)
            elif day_signal_count[ds] >= 3:
                rejections[ds]["maximo_diario"] += len(ready)
            elif ds in last_signal and (b.ts-last_signal[ds]).total_seconds() < 1200:
                rejections[ds]["cooldown"] += len(ready)
            else:
                evaluated = []
                vol20 = mean(volumes) if len(volumes) == 20 else float("nan")
                for s in ready:
                    conf = []
                    if micro_confirmation(micro_highs, micro_lows, s.side): conf.append("microestructura")
                    if len(volumes) == 20 and b.volume >= vol20: conf.append("volumen")
                    if idx >= 5 and b.atr is not None and bars[idx-5].atr is not None and b.atr >= bars[idx-5].atr:
                        conf.append("atr_creciente")
                    if s.level_kind in ("vwap", "vwap_plus1", "vwap_minus1"):
                        conf.append("vwap")
                    if len(conf) < 2:
                        rejections[ds]["confirmaciones_menores_a_2"] += 1
                        continue
                    entry = tick(b.close + TICK if s.side == "BUY" else b.close-TICK)
                    stop = tick(s.event_extreme-TICK if s.side == "BUY" else s.event_extreme+TICK)
                    risk = entry-stop if s.side == "BUY" else stop-entry
                    if not b.atr or risk < 1 or risk > 2*b.atr:
                        rejections[ds]["stop_invalido"] += 1
                        continue
                    raw_tp = entry + 1.5*risk if s.side == "BUY" else entry-1.5*risk
                    tp1 = tick(raw_tp)
                    blocked = False
                    for other in candidates:
                        if not other.active or other.ident == s.level_id:
                            continue
                        if s.side == "BUY" and other.lower > entry and other.lower < tp1:
                            blocked = True; break
                        if s.side == "SELL" and other.upper < entry and other.upper > tp1:
                            blocked = True; break
                    if blocked:
                        rejections[ds]["nivel_contrario_antes_tp1"] += 1
                        continue
                    evaluated.append((len(conf), -abs(b.close-(s.lower+s.upper)/2), s, entry, stop, risk, tp1, conf, vol20))
                if evaluated:
                    _, _, s, entry, stop, risk, tp1, conf, vol20 = max(evaluated, key=lambda x: (x[0], x[1], x[2].level_id))
                    active_trade = Trade(ds, b.ts, s.side, s.level_kind, s.event_type, entry, stop, risk,
                                         tp1, b.atr, b.volume, vol20, conf)
                    trades.append(active_trade)
                    day_signal_count[ds] += 1
                    last_signal[ds] = b.ts
            for s in ready:
                setups.pop((s.level_id, s.side), None)
        volumes.append(b.volume)

    if active_trade:
        active_trade.result = "OPEN"
        active_trade.result_r = 0.0

    daily = []
    by_day = defaultdict(list)
    for t in trades:
        by_day[t.entry_day].append(t)
    equity, peak, max_dd = 0.0, 0.0, 0.0
    curve = []
    for t in trades:
        equity += t.result_r or 0
        peak = max(peak, equity)
        max_dd = max(max_dd, peak-equity)
        curve.append({"timestamp": (t.exit_ts or t.ts).isoformat(), "equity_r": round(equity, 6)})
    for ds in date_strings:
        dtr = by_day[ds]
        rvals = [t.result_r or 0 for t in dtr]
        run_r = peak_d = dd = 0.0
        for r in rvals:
            run_r += r; peak_d = max(peak_d, run_r); dd = max(dd, peak_d-run_r)
        daily.append({"date": ds, "signals": len(dtr), "wins": sum(t.result=="TP1" for t in dtr),
                      "losses": sum(t.result=="STOP" for t in dtr), "open": sum(t.result=="OPEN" for t in dtr),
                      "result_r": round(sum(rvals), 6), "intraday_drawdown_r": round(dd, 6),
                      "rejections": dict(rejections[ds])})
    closed = [t for t in trades if t.result in ("TP1", "STOP")]
    wins = [t.result_r for t in closed if t.result_r > 0]
    losses = [t.result_r for t in closed if t.result_r < 0]
    global_result = {"calendar_dates": len(date_strings), "trades": len(trades), "closed": len(closed),
                     "open": len(trades)-len(closed), "wins": len(wins), "losses": len(losses),
                     "winrate_pct": round(100*len(wins)/len(closed), 4) if closed else 0,
                     "total_r": round(sum((t.result_r or 0) for t in trades), 6),
                     "profit_factor": round(sum(wins)/abs(sum(losses)), 6) if losses else None,
                     "max_drawdown_r": round(max_dd, 6),
                     "trades_per_day": round(len(trades)/len(date_strings), 6),
                     "distribution_r": dict(Counter(str(round(t.result_r or 0, 4)) for t in trades)),
                     "rejections": dict(sum((rejections[d] for d in rejections), Counter()))}
    return trades, daily, curve, global_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("backtest_v22_results"))
    args = parser.parse_args()
    bars = read_bars(args.source)
    trades, daily, curve, summary = run(bars)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output/"trades.csv").open("w", newline="", encoding="utf-8") as fh:
        fields = ["entry_day","ts","side","level","event","entry","stop","risk","tp1","atr","volume","volume20","confirmations","result","result_r","exit_ts"]
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader()
        for t in trades:
            row = t.__dict__.copy(); row["ts"] = t.ts.isoformat(); row["exit_ts"] = t.exit_ts.isoformat() if t.exit_ts else ""; row["confirmations"] = ",".join(t.confirmations); writer.writerow(row)
    (args.output/"daily.json").write_text(json.dumps(daily, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.output/"equity_curve.json").write_text(json.dumps(curve, indent=2), encoding="utf-8")
    (args.output/"summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
