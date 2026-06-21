# BiUmolo

BiUmolo is a Windows/NinjaTrader research prototype that receives closed NQ
minute bars over WebSocket, evaluates market structure, and delivers validated
signals to NinjaTrader and Telegram.

## Current status

**Level 2: functional prototype.** Infrastructure is operational, but no
production trading edge has been demonstrated. Do not use real capital.

Known validation status:

- Backend and `/stream` WebSocket operate locally.
- Stale/future live bars are rejected before the pipeline.
- Basic console logging is enabled.
- BiUmolo v2.3 is specified but not integrated into production.
- v2.2 produced only a marginal positive result before full costs.
- Offline v2.3 and 20-30 session forward validation remain required.

## Requirements

- Windows
- Python 3.11
- NinjaTrader 8
- A market-data connection for meaningful paper testing

## Setup

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. Never commit `.env`.

## Run locally

```powershell
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Expected connection message:

```text
NinjaTrader conectado via /stream
```

## Verify

```powershell
python -m compileall -q .
python -m unittest discover -s tests -v
python auditor_biumolo_pro_v2.py
```

## Repository policy

Market data, logs, generated reports, credentials, and NinjaTrader import files
are intentionally excluded. Dataset identity must be recorded by hash in an
external validation record; raw datasets remain outside Git.

See `docs/` for architecture, operating modes, datasets, and validation state.

