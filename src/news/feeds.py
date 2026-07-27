"""RSS fetching and normalization via feedparser.

A broken/unreachable feed is logged and skipped so one bad URL never fails a run.
"""

from __future__ import annotations

import calendar
import re
import time
from typing import Any

import feedparser
import requests

_HTML_TAG = re.compile(r"<[^>]+>")
# feedparser sets a UA, but some feeds 403 the default; use a browser-ish one.
_UA = "Mozilla/5.0 (compatible; DiscordPushBot/1.0; +https://github.com/)"
_ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"
# Hard per-feed timeout. feedparser.parse(url) has NO timeout by default, so a
# single hung server could stall the whole run for many minutes — we fetch with
# requests (which does time out) and hand the bytes to feedparser instead.
_FEED_TIMEOUT = 20


def _entry_epoch(entry: Any) -> float | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None) or (entry.get(attr) if hasattr(entry, "get") else None)
        if t:
            try:
                return calendar.timegm(t)  # struct_time is UTC
            except Exception:
                continue
    return None


def _clean(text: str) -> str:
    return _HTML_TAG.sub("", text or "").strip()


def fetch_feed(url: str) -> list[dict[str, Any]]:
    """Fetch a single feed, returning normalized entries. Never raises.

    Fetches with a hard timeout so one unresponsive feed can't hang the run,
    then parses the returned bytes with feedparser.
    """
    try:
        resp = requests.get(
            url, headers={"User-Agent": _UA, "Accept": _ACCEPT}, timeout=_FEED_TIMEOUT
        )
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:
        print(f"  [feed] error fetching {url}: {exc}")
        return []
    if getattr(parsed, "bozo", 0) and not parsed.entries:
        print(f"  [feed] unparseable / empty: {url}")
        return []

    source = _clean(getattr(parsed.feed, "title", "")) or url
    items: list[dict[str, Any]] = []
    for e in parsed.entries:
        link = getattr(e, "link", "") or ""
        title = _clean(getattr(e, "title", ""))
        if not title or not link:
            continue
        summary = _clean(getattr(e, "summary", "") or getattr(e, "description", ""))
        items.append(
            {
                "title": title,
                "link": link,
                "summary": summary[:600],
                "source": source,
                "epoch": _entry_epoch(e),
            }
        )
    return items


def fetch_recent(
    urls: list[str],
    within_seconds: float,
    *,
    min_items: int = 0,
    max_items: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch many feeds and return recent entries, newest first.

    Primary result is entries published within `within_seconds`. If fewer than
    `min_items` fall inside that window (e.g. a quiet news day, or timestamps that
    don't line up), fall back to the newest `max_items` entries regardless of date
    so a digest is never starved. Leave `min_items=0` (the default) to disable the
    fallback — that's what the urgent scanner uses, since it must only surface
    genuinely-recent items.
    """
    cutoff = time.time() - within_seconds
    keep_undated = within_seconds >= 3 * 3600  # digests keep undated; urgent doesn't

    seen_links: set[str] = set()
    all_items: list[dict[str, Any]] = []
    for url in urls:
        for item in fetch_feed(url):
            if item["link"] in seen_links:
                continue
            seen_links.add(item["link"])
            all_items.append(item)

    # Newest first (undated sink to the bottom).
    all_items.sort(key=lambda x: x["epoch"] or 0, reverse=True)

    recent = [
        it for it in all_items
        if (it["epoch"] and it["epoch"] >= cutoff) or (keep_undated and not it["epoch"])
    ]
    result = recent if len(recent) >= min_items else all_items
    return result[:max_items] if max_items else result
