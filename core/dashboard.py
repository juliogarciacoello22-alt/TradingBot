import datetime

def update_dashboard(candle, micro, signal):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""
    <html>
    <head>
        <meta http-equiv="refresh" content="1">
        <style>
            body {{
                background-color: #0d0d0d;
                color: #e6e6e6;
                font-family: Arial, sans-serif;
                padding: 20px;
            }}
            .box {{
                background-color: #1a1a1a;
                padding: 15px;
                margin-bottom: 15px;
                border-radius: 8px;
                border: 1px solid #333;
            }}
            h2 {{
                color: #4da6ff;
            }}
            .good {{
                color: #00ff99;
            }}
            .bad {{
                color: #ff4d4d;
            }}
        </style>
    </head>
    <body>

        <h1>BIUMOLO — DASHBOARD INSTITUCIONAL</h1>
        <p>Última actualización: {now}</p>

        <div class="box">
            <h2>Vela actual</h2>
            <p>Open: {candle.open}</p>
            <p>High: {candle.high}</p>
            <p>Low: {candle.low}</p>
            <p>Close: {candle.close}</p>
            <p>Volume: {candle.volume}</p>
        </div>

        <div class="box">
            <h2>Microestructura</h2>
            <pre>{micro}</pre>
        </div>

        <div class="box">
            <h2>Señal</h2>
            <p>Dirección: {signal.get("direction") if signal else None}</p>
            <p>Entry: {signal.get("entry") if signal else None}</p>
            <p>Stop: {signal.get("stop") if signal else None}</p>
            <p>TP1: {signal.get("tp1") if signal else None}</p>
            <p>TP2: {signal.get("tp2") if signal else None}</p>
            <p>TP3: {signal.get("tp3") if signal else None}</p>
            <p>Grade: {signal.get("grade") if signal else None}</p>
        </div>

    </body>
    </html>
    """

    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(html)
