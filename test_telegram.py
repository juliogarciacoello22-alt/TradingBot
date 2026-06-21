from dotenv import load_dotenv
load_dotenv()

import os
print("TOKEN:", os.getenv("TELEGRAM_TOKEN"))
print("CHAT:", os.getenv("TELEGRAM_CHAT_ID"))

from core.telegram_bot import TelegramBot
bot = TelegramBot()
bot.send("🔥 Test de Telegram desde el TradingBot — OK")
