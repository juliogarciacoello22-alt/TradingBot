# core/tp_engine.py

class TPEngine:
    """
    TPEngine PRO — Institucional
    ----------------------------
    TP1 → Liquidez inmediata (swing cercano)
    TP2 → FVG midpoint o swing institucional
    TP3 → Liquidez externa (EQH/EQL)

    CONTRATO:
        BUY  → entry < TP1 < TP2 < TP3
        SELL → entry > TP1 > TP2 > TP3
    """

    def __init__(self):
        pass

    # ============================================================
    #   1. TP1 — Liquidez inmediata (swing cercano)
    # ============================================================
    def tp1_liquidity(self, side, micro):
        try:
            swing = micro.get("swing", {})
            swing_high = swing.get("high")
            swing_low  = swing.get("low")

            if side == "BUY" and swing_high:
                return swing_high.get("price")

            if side == "SELL" and swing_low:
                return swing_low.get("price")

            return None

        except Exception as e:
            print("ERROR EN TP ENGINE (tp1):", e)
            return None

    # ============================================================
    #   2. TP2 — FVG midpoint o swing institucional
    # ============================================================
    def tp2_midpoint(self, side, micro):
        try:
            fvg = micro.get("fvg")

            # midpoint institucional
            if fvg and "high" in fvg and "low" in fvg:
                return (fvg["high"] + fvg["low"]) / 2

            # fallback institucional
            swing = micro.get("swing", {})
            swing_high = swing.get("high")
            swing_low  = swing.get("low")

            if side == "BUY" and swing_high:
                return swing_high.get("price")

            if side == "SELL" and swing_low:
                return swing_low.get("price")

            return None

        except Exception as e:
            print("ERROR EN TP ENGINE (tp2):", e)
            return None

    # ============================================================
    #   3. TP3 — Liquidez externa (EQH/EQL)
    # ============================================================
    def tp3_external_liquidity(self, side, micro):
        try:
            liq = micro.get("liquidity", {}) or {}

            # BUY → buscar EQH externos
            if side == "BUY" and liq.get("external_liquidity") == "highs":
                swing = micro.get("swing", {})
                sh = swing.get("high")
                return sh.get("price") if sh else None

            # SELL → buscar EQL externos
            if side == "SELL" and liq.get("external_liquidity") == "lows":
                swing = micro.get("swing", {})
                sl = swing.get("low")
                return sl.get("price") if sl else None

            return None

        except Exception as e:
            print("ERROR EN TP ENGINE (tp3):", e)
            return None

    # ============================================================
    #   4. NORMALIZADOR INSTITUCIONAL (SIN DUPLICADOS)
    # ============================================================
    def _normalize(self, side, entry, stop, tps):
        """
        BUY  → entry < TP1 < TP2 < TP3
        SELL → entry > TP1 > TP2 > TP3
        """

        # eliminar None
        tps = [tp for tp in tps if tp is not None]

        # eliminar duplicados exactos
        tps = list(dict.fromkeys(tps))

        risk = abs(entry - stop)

        # ------------------------------------------------------------
        # BUY
        # ------------------------------------------------------------
        if side == "BUY":
            # filtrar TPs inválidos
            tps = [tp for tp in tps if tp > entry]

            # completar faltantes con niveles institucionales
            while len(tps) < 3:
                next_tp = entry + risk * (1.5 + 0.5 * len(tps))
                if next_tp not in tps:
                    tps.append(next_tp)

            # ordenar ascendente
            tps = sorted(tps)

        # ------------------------------------------------------------
        # SELL
        # ------------------------------------------------------------
        else:
            tps = [tp for tp in tps if tp < entry]

            while len(tps) < 3:
                next_tp = entry - risk * (1.5 + 0.5 * len(tps))
                if next_tp not in tps:
                    tps.append(next_tp)

            tps = sorted(tps, reverse=True)

        # devolver EXACTAMENTE 3 niveles
        return tps[:3]

    # ============================================================
    #   5. GENERAR TP COMPLETOS (CONTRATO INSTITUCIONAL)
    # ============================================================
    def generate_tp(self, side, micro, entry, stop):
        try:
            tp1 = self.tp1_liquidity(side, micro)
            tp2 = self.tp2_midpoint(side, micro)
            tp3 = self.tp3_external_liquidity(side, micro)

            # normalizar institucionalmente
            tps = self._normalize(side, entry, stop, [tp1, tp2, tp3])

            return tps[0], tps[1], tps[2]

        except Exception as e:
            print("ERROR EN TP ENGINE (generate_tp):", e)
            rr = abs(entry - stop)

            # fallback institucional seguro
            if side == "BUY":
                return entry + rr, entry + rr * 2, entry + rr * 3
            else:
                return entry - rr, entry - rr * 2, entry - rr * 3
