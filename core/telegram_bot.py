import os
import requests
import time

class TelegramBot:
    def __init__(self, token=None, chat_id=None):
        # Carga automatica desde .env si no se pasan argumentos
        self.token = token or os.getenv("TELEGRAM_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

        if not self.token or not self.chat_id:
            raise ValueError("❌ TelegramBot: token o chat_id no configurados. Revisa tu .env")

        self.url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        self.max_len = 3900  # margen seguro para HTML

    # ============================================================
    #   DIVIDIR MENSAJES LARGOS (CRÍTICO)
    # ============================================================
    def _split_message(self, text):
        if len(text) <= self.max_len:
            return [text]

        parts = []
        while len(text) > self.max_len:
            chunk = text[:self.max_len]
            parts.append(chunk)
            text = text[self.max_len:]
        parts.append(text)
        return parts

    # ============================================================
    #   ENVÍO SEGURO CON RETRY
    # ============================================================
    def _send_chunk(self, chunk, retries=3):
        payload = {
            "chat_id": self.chat_id,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        for attempt in range(retries):
            try:
                r = requests.post(self.url, json=payload, timeout=5)

                # Error HTTP
                if r.status_code != 200:
                    print(f"❌ Telegram error HTTP {r.status_code}: {r.text}")

                    # Rate limit -> esperar y reintentar
                    if r.status_code == 429:
                        time.sleep(1.5)
                        continue

                    return None

                return r.json()

            except Exception as e:
                print(f"❌ Error enviando a Telegram (intento {attempt+1}):", e)
                time.sleep(1)

        return None

    # ============================================================
    #   API PUBLICA
    # ============================================================
    def send(self, text):
        if not isinstance(text, str):
            text = str(text)

        print(">>> ENVIANDO A TELEGRAM...")

        chunks = self._split_message(text)

        results = []
        for chunk in chunks:
            res = self._send_chunk(chunk)
            results.append(res)

        print(">>> TELEGRAM COMPLETADO")
        return results
