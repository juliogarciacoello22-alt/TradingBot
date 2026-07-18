import pytest

from core import telegram_bot


@pytest.fixture(autouse=True)
def block_unmocked_http(monkeypatch):
    def fail_on_real_http(*args, **kwargs):
        raise AssertionError("Unexpected real HTTP request")

    monkeypatch.setattr(telegram_bot.requests, "post", fail_on_real_http)


def test_telegram_bot_requires_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    with pytest.raises(ValueError, match="token o chat_id no configurados"):
        telegram_bot.TelegramBot()


def test_telegram_send_uses_fake_credentials_and_mocked_http(monkeypatch):
    monkeypatch.setenv("TELEGRAM_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "fake-chat-id")
    calls = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    def fake_post(url, *, json, timeout):
        calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(telegram_bot.requests, "post", fake_post)

    bot = telegram_bot.TelegramBot()
    result = bot.send("deterministic test message")

    assert result == [{"ok": True}]
    assert calls == [
        {
            "url": "https://api.telegram.org/botfake-token/sendMessage",
            "json": {
                "chat_id": "fake-chat-id",
                "text": "deterministic test message",
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            "timeout": 5,
        }
    ]
