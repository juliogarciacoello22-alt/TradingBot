import os
import json

def log_trade(trade):
    os.makedirs("logs", exist_ok=True)
    path = os.path.join("logs", "trades.log")
    with open(path, "a") as f:
        f.write(json.dumps(trade) + "\n")
