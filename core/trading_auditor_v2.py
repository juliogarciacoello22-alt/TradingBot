import json
import os
from datetime import datetime

class TradingAuditorV2:
    def __init__(self, signals_path: str):
        self.signals_path = signals_path
        self.signals = []

    # ============================================================
    #   CARGA DE SEÑALES
    # ============================================================
    def load_signals(self):
        if not os.path.exists(self.signals_path):
            print(f"[AuditorV2] No existe el archivo de señales: {self.signals_path}")
            return

        with open(self.signals_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    self.signals.append(json.loads(line))
                except Exception:
                    continue

    # ============================================================
    #   ESTADÍSTICAS BÁSICAS
    # ============================================================
    def _basic_stats(self):
        total = len(self.signals)
        longs = sum(1 for s in self.signals if s.get("side") == "buy")
        shorts = sum(1 for s in self.signals if s.get("side") == "sell")

        return {
            "total_signals": total,
            "longs": longs,
            "shorts": shorts,
        }

    # ============================================================
    #   RIESGO
    # ============================================================
    def _risk_stats(self):
        risks = []
        for s in self.signals:
            meta = s.get("meta", {})
            risk = meta.get("risk", {})
            if isinstance(risk, dict) and "r" in risk:
                risks.append(risk["r"])

        if not risks:
            return {}

        return {
            "avg_risk_R": sum(risks) / len(risks),
            "max_risk_R": max(risks),
            "min_risk_R": min(risks),
        }

    # ============================================================
    #   MICROESTRUCTURA
    # ============================================================
    def _micro_stats(self):
        stats = {
            "momentum": 0,
            "sweep": 0,
            "inducement": 0,
            "breaker": 0,
            "absorption": 0,
            "fake_displacement": 0,
            "ob_present": 0,
            "premium": 0,
            "discount": 0,
            "fvg": 0,
        }

        for s in self.signals:
            micro = s.get("micro", {})

            for key in stats.keys():
                if micro.get(key):
                    stats[key] += 1

        return stats

    # ============================================================
    #   SESIONES
    # ============================================================
    def _session_stats(self):
        sessions = {"NY": 0, "London": 0, "Asia": 0, "Unknown": 0}

        for s in self.signals:
            timing = s.get("timing", {})
            session = timing.get("session", "Unknown")
            sessions[session] = sessions.get(session, 0) + 1

        return sessions

    # ============================================================
    #   HORAS
    # ============================================================
    def _hour_stats(self):
        hours = {}

        for s in self.signals:
            ts = s.get("timestamp")
            if not ts:
                continue

            hour = datetime.fromtimestamp(ts).hour
            hours[hour] = hours.get(hour, 0) + 1

        return hours

    # ============================================================
    #   DÍAS
    # ============================================================
    def _day_stats(self):
        days = {}

        for s in self.signals:
            ts = s.get("timestamp")
            if not ts:
                continue

            day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            days[day] = days.get(day, 0) + 1

        return days

    # ============================================================
    #   OVERTRADING (señales muy seguidas)
    # ============================================================
    def _overtrading(self):
        if len(self.signals) < 2:
            return 0

        count = 0
        last_ts = None

        for s in self.signals:
            ts = s.get("timestamp")
            if last_ts is not None:
                if ts - last_ts < 60:  # menos de 1 minuto
                    count += 1
            last_ts = ts

        return count

    # ============================================================
    #   SEÑALES DUPLICADAS (misma dirección + mismo contexto)
    # ============================================================
    def _duplicates(self):
        seen = set()
        duplicates = 0

        for s in self.signals:
            key = (
                s.get("side"),
                s.get("context", {}).get("trend"),
                s.get("micro", {}).get("momentum"),
                s.get("micro", {}).get("ob"),
            )
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)

        return duplicates

    # ============================================================
    #   INTENSIDAD INSTITUCIONAL
    # ============================================================
    def _institutional_strength(self):
        scores = []

        for s in self.signals:
            micro = s.get("micro", {})
            score = 0

            if micro.get("momentum"): score += 1
            if micro.get("sweep"): score += 1
            if micro.get("inducement"): score += 1
            if micro.get("breaker"): score += 1
            if micro.get("ob"): score += 1
            if micro.get("premium") or micro.get("discount"): score += 1
            if micro.get("fvg"): score += 1

            scores.append(score)

        if not scores:
            return {}

        return {
            "avg_strength": sum(scores) / len(scores),
            "max_strength": max(scores),
            "min_strength": min(scores),
        }

    # ============================================================
    #   REPORTE FINAL
    # ============================================================
    def report(self):
        self.load_signals()

        basic = self._basic_stats()
        risk = self._risk_stats()
        micro = self._micro_stats()
        sessions = self._session_stats()
        hours = self._hour_stats()
        days = self._day_stats()
        over = self._overtrading()
        dup = self._duplicates()
        strength = self._institutional_strength()

        print("========== TRADING AUDITOR V2 (AVANZADO) ==========")
        print(">> Señales")
        print(f"   Total:  {basic['total_signals']}")
        print(f"   Longs:  {basic['longs']}")
        print(f"   Shorts: {basic['shorts']}")

        print("\n>> Riesgo")
        if risk:
            print(f"   Riesgo medio (R): {risk['avg_risk_R']:.2f}")
            print(f"   Riesgo máx (R):   {risk['max_risk_R']:.2f}")
            print(f"   Riesgo mín (R):   {risk['min_risk_R']:.2f}")
        else:
            print("   No hay datos de riesgo.")

        print("\n>> Microestructura")
        for k, v in micro.items():
            print(f"   {k}: {v}")

        print("\n>> Sesiones")
        for k, v in sessions.items():
            print(f"   {k}: {v}")

        print("\n>> Señales por hora")
        for k, v in sorted(hours.items()):
            print(f"   {k}:00 → {v} señales")

        print("\n>> Señales por día")
        for k, v in sorted(days.items()):
            print(f"   {k}: {v}")

        print("\n>> Overtrading")
        print(f"   Señales demasiado seguidas: {over}")

        print("\n>> Duplicadas")
        print(f"   Señales duplicadas: {dup}")

        print("\n>> Intensidad institucional")
        if strength:
            print(f"   Fuerza media: {strength['avg_strength']:.2f}")
            print(f"   Máxima:       {strength['max_strength']}")
            print(f"   Mínima:       {strength['min_strength']}")
        else:
            print("   No hay datos.")

        print("====================================================")
