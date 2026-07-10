\# Blocked Server Startup Smoke Test



\## Purpose



Validate that the FastAPI server can start, answer a passive HTTP request, and stop cleanly while trading remains blocked.



\## Safe Environment



\- `RUN\_MODE=PLAYBACK`

\- `ENABLE\_TRADING=false`

\- `TRADING\_ACCOUNT=playback`

\- `TELEGRAM\_ENABLED=false`

\- `LIVE\_TRADING\_APPROVED=false`



\## Command



```powershell

python tools/server\_startup\_smoke.py

