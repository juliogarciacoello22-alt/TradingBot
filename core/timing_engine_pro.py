# core/timing_engine_pro.py

from datetime import datetime, time


class TimingEngine:
    """
    TIMING ENGINE PRO — BIUMOLO INSTITUTIONAL
    -----------------------------------------
    Controla:
    - Sesiones (Asia, London, NY)
    - Killzones institucionales
    - Dead zones
    - Premarket NY
    - Lunch time NY
    - Cierre CME
    - Volatilidad
    - News (placeholder)
    - Score institucional
    - Contrato compatible con SignalEngine V4 PRO
    """

    def __init__(self):
        pass

    # ============================================================
    #   1. SESIONES
    # ============================================================
    def detect_session(self, now):
        t = now.time()

        asia_open   = time(18, 0)
        asia_close  = time(3, 0)

        london_open = time(2, 0)
        london_close = time(7, 0)

        ny_open     = time(7, 0)
        ny_close    = time(16, 0)

        # Asia (18:00 – 03:00)
        if t >= asia_open or t < london_open:
            return "asia"

        # London (02:00 – 07:00)
        if london_open <= t < ny_open:
            return "london"

        # New York (07:00 – 16:00)
        if ny_open <= t <= ny_close:
            return "ny"

        return "dead"

    # ============================================================
    #   2. KILLZONES INSTITUCIONALES
    # ============================================================
    def detect_killzone(self, now):
        t = now.time()

        # London Killzone (02:00 – 05:00)
        if time(2, 0) <= t < time(5, 0):
            return "london_killzone"

        # NY Killzone (07:00 – 10:00)
        if time(7, 0) <= t < time(10, 0):
            return "ny_killzone"

        # NY PM Session (13:00 – 16:00)
        if time(13, 0) <= t <= time(16, 0):
            return "ny_pm"

        return "none"

    # ============================================================
    #   3. DEAD ZONES
    # ============================================================
    def detect_deadzone(self, now):
        t = now.time()

        # Lunch time NY (11:30 – 13:00)
        if time(11, 30) <= t < time(13, 0):
            return True

        # After CME close (16:00 – 18:00)
        if time(16, 0) <= t < time(18, 0):
            return True

        return False

    # ============================================================
    #   4. VOLATILIDAD
    # ============================================================
    def detect_volatility(self, tf):
        candles = tf.get("1m", [])
        if len(candles) < 5:
            return "normal"

        last = candles[-1]
        prev = candles[-5]

        if last.range > prev.range * 1.8:
            return "high"

        if last.range < prev.range * 0.5:
            return "low"

        return "normal"

    # ============================================================
    #   5. NEWS (placeholder)
    # ============================================================
    def detect_news(self, now):
        return False

    # ============================================================
    #   6. SCORE INSTITUCIONAL
    # ============================================================
    def compute_score(self, session, killzone, vol, news):
        score = 0

        if session == "london":
            score += 2
        if session == "ny":
            score += 2
        if session == "asia":
            score += 1

        if killzone in ("london_killzone", "ny_killzone"):
            score += 2

        if vol == "high":
            score += 2
        if vol == "normal":
            score += 1

        if news:
            score -= 3

        return score

    # ============================================================
    #   7. API PRINCIPAL
    # ============================================================
    def build_timing(self, tf, now=None):
        if now is None:
            now = datetime.now()

        session   = self.detect_session(now)
        killzone  = self.detect_killzone(now)
        deadzone  = self.detect_deadzone(now)
        vol       = self.detect_volatility(tf)
        news      = self.detect_news(now)

        score = self.compute_score(session, killzone, vol, news)

        valid = True
        reason = "ok"

        # Dead zones → NO TRADE
        if session == "dead":
            valid = False
            reason = "dead session"

        if deadzone:
            valid = False
            reason = "deadzone"

        # Volatilidad extremadamente baja → NO TRADE
        if vol == "low":
            valid = False
            reason = "low volatility"

        # News → NO TRADE
        if news:
            valid = False
            reason = "news"

        return {
            "valid": valid,
            "session": session,
            "killzone": killzone,
            "volatility": vol,
            "news": news,
            "reason": reason,
            "score": score
        }
