import json
from collections import Counter, defaultdict

LOG_FILE = "biumolo_institucional.log"

def main():
    events = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except:
                continue

    total = len(events)
    print(f"\n===== TOTAL DE EVENTOS: {total} =====")

    # Contar tipos de evento
    event_types = Counter(e["event"] for e in events)
    print("\n===== TIPOS DE EVENTO =====")
    for k, v in event_types.items():
        print(f"{k}: {v}")

    # Contar razones
    reasons = Counter(e["reason"] for e in events)
    print("\n===== RAZONES =====")
    for r, c in reasons.most_common():
        print(f"{c}x - {r}")

    # BUY vs SELL
    sides = Counter(e["type"] for e in events)
    print("\n===== BUY vs SELL =====")
    for s, c in sides.items():
        print(f"{s}: {c}")

    # Entradas más comunes
    entries = Counter(e["entry"] for e in events)
    print("\n===== ENTRADAS MÁS FRECUENTES =====")
    for price, c in entries.most_common(10):
        print(f"{price}: {c} veces")

    # Stops más comunes
    stops = Counter(e["stop"] for e in events)
    print("\n===== STOPS MÁS FRECUENTES =====")
    for price, c in stops.most_common(10):
        print(f"{price}: {c} veces")

if __name__ == "__main__":
    main()
