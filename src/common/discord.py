"""Discord webhook posting with basic rate-limit handling.

Embeds are Discord's rich-message format. Each stream (cards, cyber, tech, ai,
urgent) posts to its own webhook URL so they land in separate channels.
"""

from __future__ import annotations

import time
from typing import Any

import requests

# Discord brand-ish colours per stream (decimal ints).
COLORS = {
    "cards": 0xF1C40F,   # gold
    "cyber": 0xE74C3C,   # red
    "tech": 0x3498DB,    # blue
    "ai": 0x9B59B6,      # purple
    "urgent": 0xC0392B,  # dark red
}

_MAX_EMBEDS_PER_MESSAGE = 10
_TIMEOUT = 30


def _post(webhook_url: str, payload: dict[str, Any]) -> None:
    """POST one payload, retrying once on HTTP 429 (rate limit)."""
    for attempt in range(2):
        resp = requests.post(webhook_url, json=payload, timeout=_TIMEOUT)
        if resp.status_code == 429:
            retry_after = 1.0
            try:
                retry_after = float(resp.json().get("retry_after", 1.0))
            except Exception:
                pass
            time.sleep(min(retry_after + 0.25, 10))
            continue
        resp.raise_for_status()
        return
    resp.raise_for_status()


def send_embeds(webhook_url: str, embeds: list[dict[str, Any]], content: str = "") -> None:
    """Send embeds to a webhook, chunked to Discord's 10-embeds-per-message limit."""
    if not webhook_url:
        print("  [discord] no webhook configured for this stream; skipping send")
        return
    if not embeds:
        if content:
            _post(webhook_url, {"content": content})
        return

    first = True
    for i in range(0, len(embeds), _MAX_EMBEDS_PER_MESSAGE):
        chunk = embeds[i : i + _MAX_EMBEDS_PER_MESSAGE]
        payload: dict[str, Any] = {"embeds": chunk}
        if first and content:
            payload["content"] = content[:2000]
            first = False
        _post(webhook_url, payload)
        time.sleep(0.4)  # gentle spacing between messages


def make_embed(
    *,
    title: str,
    description: str = "",
    url: str | None = None,
    color: int | None = None,
    fields: list[dict[str, Any]] | None = None,
    thumbnail_url: str | None = None,
    footer: str | None = None,
    timestamp_iso: str | None = None,
) -> dict[str, Any]:
    embed: dict[str, Any] = {"title": title[:256]}
    if description:
        embed["description"] = description[:4096]
    if url:
        embed["url"] = url
    if color is not None:
        embed["color"] = color
    if fields:
        embed["fields"] = fields[:25]
    if thumbnail_url:
        embed["thumbnail"] = {"url": thumbnail_url}
    if footer:
        embed["footer"] = {"text": footer[:2048]}
    if timestamp_iso:
        embed["timestamp"] = timestamp_iso
    return embed
