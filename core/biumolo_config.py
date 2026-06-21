SHOW_STARTUP_STATUS = True
BASIC_LOG_ONLY = True

# Closed 1m bars may use their opening timestamp, so two minutes allows the
# bar to close and cross the WebSocket without accepting historical data.
MAX_LIVE_BAR_DRIFT_SECONDS = 120
