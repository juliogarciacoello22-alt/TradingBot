# core/trading_results_auditor.py

import os
import json
from datetime import datetime
from collections import defaultdict

class TradingResultsAuditor:
    def __init__(self, trades_path: str = "logs/trades.log"):
        self.trades_path = trades_path
        self.trades = []

    # ------------------------------------------------------------
    #   CARGAR TRADES
    # ------------------------------------------------------------
    def load_trades(self):
        self.trades = []

        if not os.path.exists(self.trades_path):
            print(f"[Auditor] No existe {self.trades_path}")
            return

        with open(self.trades_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.trades.append(json.loads(line))
                except:
                    continue

    # ------------------------------------------------------------
    #   ESTADÍSTICAS BÁSICAS
    # ------------------------------------------------------------
    def basic_stats(self):
        total = len(self.trades)
        wins = sum(1 for t in self.trades if t.get("result_R", 0) > 0)
        losses = sum(1 for t in self.trades if t.get("result_R", 0) < 0)
        be = total - wins - losses

        return {
            "total": total,
            "wins": wins,
            "losses": losses,
            "breakeven": be,
            "winrate": (wins / total * 100) if total > 0 else 0
        }

    # ------------------------------------------------------------
    #   PNL EN R
    # ------------------------------------------------------------
    def pnl_stats(self):
        results = [t.get("result_R", 0) for t in self.trades]
        if not results:
            return {}

        total_R = sum(results)
        avg_R = total_R / len(results)
        max_win = max(results)
        max_loss = min(results)

        return {
            "total_R": total_R,
            "avg_R": avg_R,
            "max_win": max_win,
            "max_loss": max_loss,
        }

    # ------------------------------------------------------------
    #   EXPECTATIVA
    # ------------------------------------------------------------
    def expectancy(self):
        if not self.trades:
            return 0

        wins = [t.get("result_R", 0) for t in self.trades if t.get("result_R", 0) > 0]
        losses = [t.get("result_R", 0) for t in self.trades if t.get("result_R", 0) < 0]

        if not wins or not losses:
            return 0

        p_win = len(wins) / len(self.trades)
        p_loss = len(losses) / len(self.trades)

        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)

        return (p_win * avg_win) + (p_loss * avg_loss)

    # ------------------------------------------------------------
    #   DRAWDOWN
    # ------------------------------------------------------------
    def max_drawdown(self):
        equity = 0
        max_equity = 0
        max_dd = 0

        for t in self.trades:
            equity += t.get("result_R", 0)
            max_equity = max(max_equity, equity)
            dd = max_equity - equity
            max_dd = max(max_dd, dd)

        return max_dd

    # ------------------------------------------------------------
    #   PROFIT FACTOR
    # ------------------------------------------------------------
    def profit_factor(self):
        wins = sum(t.get("result_R", 0) for t in self.trades if t.get("result_R", 0) > 0)
        losses = abs(sum(t.get("result_R", 0) for t in self.trades if t.get("result_R", 0) < 0))

        if losses == 0:
            return float("inf")

        return wins / losses

    # ------------------------------------------------------------
    #   TP DISTRIBUTION
    # ------------------------------------------------------------
    def tp_distribution(self):
        dist = defaultdict(int)
        for t in self.trades:
            dist[t.get("tp_hit", "None")] += 1
        return dict(dist)

    # ------------------------------------------------------------
    #   REPORTE COMPLETO
    # ------------------------------------------------------------
    def report(self):
        self.load_trades()

        print("\n========== AUDITOR DE RESULTADOS ==========")

        basic = self.basic_stats()
        pnl = self.pnl_stats()
        expectancy = self.expectancy()
        dd = self.max_drawdown()
        pf = self.profit_factor()
        tps = self.tp_distribution()

        print("\n>> ESTADÍSTICAS BÁSICAS")
        print(basic)

        print("\n>> PNL (R)")
        print(pnl)

        print("\n>> EXPECTATIVA")
        print(f"{expectancy:.3f} R por trade")

        print("\n>> DRAWDOWN MÁXIMO")
        print(f"{dd:.2f} R")

        print("\n>> PROFIT FACTOR")
        print(f"{pf:.2f}")

        print("\n>> DISTRIBUCIÓN DE TP/SL")
        print(tps)

        print("\n===========================================\n")
