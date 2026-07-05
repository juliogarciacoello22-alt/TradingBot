from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date

from .fill_model import TradeResult
from core.strategy_v23.models import Rejection


def calculate_metrics(
    trades: list[TradeResult],
    *,
    statistics_start_date: str,
    all_dates: list[str] | None = None,
    rejections: list[Rejection] | None = None,
) -> tuple[dict, list[dict], list[dict]]:
    start = date.fromisoformat(statistics_start_date)
    included = [trade for trade in trades if trade.entry_timestamp.date() >= start]
    closed = [trade for trade in included if trade.outcome in {"STOP", "TP1"}]
    wins = [trade for trade in closed if trade.net_r > 0]
    losses = [trade for trade in closed if trade.net_r < 0]
    equity = peak = max_drawdown = 0.0
    curve = []
    for trade in closed:
        equity += trade.net_r
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        curve.append({
            "sequence": trade.sequence,
            "timestamp": trade.exit_timestamp.isoformat(),
            "equity_r": round(equity, 8),
        })
    by_day = defaultdict(list)
    for trade in included:
        by_day[trade.entry_timestamp.date().isoformat()].append(trade)
    rejection_by_day = defaultdict(Counter)
    for rejection in rejections or []:
        if rejection.timestamp.date() >= start:
            rejection_by_day[rejection.timestamp.date().isoformat()][rejection.reason] += 1
    dates = sorted(set(all_dates or by_day) | set(by_day) | set(rejection_by_day))
    daily = []
    for day in dates:
        if date.fromisoformat(day) < start:
            continue
        day_trades = by_day[day]
        running = day_peak = drawdown = 0.0
        for trade in day_trades:
            running += trade.net_r
            day_peak = max(day_peak, running)
            drawdown = max(drawdown, day_peak - running)
        daily.append({
            "date": day,
            "trades": len(day_trades),
            "wins": sum(trade.net_r > 0 for trade in day_trades),
            "losses": sum(trade.net_r < 0 for trade in day_trades),
            "open": sum(trade.outcome == "OPEN" for trade in day_trades),
            "gross_r": round(sum(trade.gross_r for trade in day_trades), 8),
            "net_r": round(sum(trade.net_r for trade in day_trades), 8),
            "drawdown_r": round(drawdown, 8),
            "rejections": dict(sorted(rejection_by_day[day].items())),
        })
    total_win = sum(trade.net_r for trade in wins)
    total_loss = abs(sum(trade.net_r for trade in losses))
    summary = {
        "statistics_start_date": statistics_start_date,
        "trades": len(included),
        "closed": len(closed),
        "open": len(included) - len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "winrate_pct": round(100 * len(wins) / len(closed), 6) if closed else 0.0,
        "gross_r": round(sum(trade.gross_r for trade in included), 8),
        "exit_slippage_r": round(sum(trade.exit_slippage_r for trade in included), 8),
        "commission_r": round(sum(trade.commission_r for trade in included), 8),
        "net_r": round(sum(trade.net_r for trade in included), 8),
        "profit_factor": round(total_win / total_loss, 8) if total_loss else None,
        "max_drawdown_r": round(max_drawdown, 8),
        "distribution_net_r": dict(sorted(Counter(round(trade.net_r, 4) for trade in included).items())),
    }
    return summary, daily, curve
