from __future__ import annotations

import json
import urllib.error
import urllib.request


class TelegramError(RuntimeError):
    """Raised when Telegram delivery fails."""


MAX_TELEGRAM_TEXT_LENGTH = 4000


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    chunks = split_message(text, MAX_TELEGRAM_TEXT_LENGTH)

    for chunk in chunks:
        payload = json.dumps(
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": False,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(f"Telegram API returned HTTP {exc.code}: {details}") from exc
        except Exception as exc:
            raise TelegramError(f"Telegram request failed: {exc}") from exc

        if not body.get("ok"):
            raise TelegramError(f"Telegram API rejected the message: {body}")


def split_message(text: str, max_len: int) -> list[str]:
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > max_len:
        split_at = remaining.rfind("\n", 0, max_len)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, max_len)
        if split_at <= 0:
            split_at = max_len

        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)

        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks
