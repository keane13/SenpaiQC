"""Alert channels: Telegram bot and Google Chat incoming webhook."""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


class HttpAlertChannels:
    def __init__(self, telegram_token: str = "", telegram_chat_id: str = "", chat_webhook: str = ""):
        # Pasted secrets often carry a trailing space or newline, which Telegram answers with a 404.
        telegram_token, telegram_chat_id, chat_webhook = (v.strip() for v in (telegram_token, telegram_chat_id, chat_webhook))
        self.telegram = (telegram_token, telegram_chat_id) if telegram_token and telegram_chat_id else None
        self.chat_webhook = chat_webhook

    def names(self) -> list[str]:
        return [n for n, on in (("telegram", self.telegram), ("google-chat", self.chat_webhook)) if on]

    def deliver(self, text: str) -> list[str]:
        """Sends to every configured channel; raises if any failed, so Pub/Sub retries.

        Errors never include the URL: the Telegram one carries the bot token."""
        sent, failed = [], []
        if self.telegram:
            token, chat_id = self.telegram
            self._post("telegram", f"https://api.telegram.org/bot{token}/sendMessage",
                       {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}, sent, failed)
        if self.chat_webhook:
            self._post("google-chat", self.chat_webhook, {"text": text}, sent, failed)
        if not sent and not failed:
            log.info("alert not sent (no channel configured): %s", text.splitlines()[0])
        if failed:
            raise RuntimeError("alert delivery failed: " + ", ".join(failed))
        return sent

    @staticmethod
    def _post(name: str, url: str, body: dict, sent: list, failed: list) -> None:
        try:
            r = httpx.post(url, json=body, timeout=10)
            if r.status_code >= 300:
                failed.append(f"{name} HTTP {r.status_code}")
            else:
                sent.append(name)
        except httpx.HTTPError as exc:
            failed.append(f"{name} {type(exc).__name__}")
