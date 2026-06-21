@echo off
title TradingBot - FastAPI Server
echo Iniciando servidor...
uvicorn server:app --host 0.0.0.0 --port 8000
pause
