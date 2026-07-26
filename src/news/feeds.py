"""RSS fetching and normalization via feedparser.

A broken/unreachable feed is logged and skipped so one bad URL never fails a run.
"""

from __future__ import annotations

import calendar
import re
import time
from typing import Any

import feedparser

_HTML_TAG = re.compile(r"<[^>]+>")
# feedparser sets a UA, but some feeds 403 the default; use a browser-ish one.
_UA = "Mozilla/5.0 (compatible; DiscordPushBot/1.0; +https://github.com/)"


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
    """Fetch a single feed, returning normalized entries. Never raises."""
    try:
        parsed = feedparser.parse(url, agent=_UA)
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


def fetch_recent(urls: list[str], within_seconds: float) -> list[dict[str, Any]]:
    """Fetch many feeds and return entries published within `within_seconds`.

    Entries with no parseable date are kept only for short windows (< 3h) to avoid
    flooding urgent alerts, but always kept for daily digests (long windows).
    """
    cutoff = time.time() - within_seconds
    keep_undated = within_seconds >= 3 * 3600
    seen_links: set[str] = set()
    out: list[dict[str, Any]] = []
    for url in urls:
        for item in fetch_feed(url):
            link = item["link"]
            if link in seen_links:
                continue
            epoch = item["epoch"]
            if epoch is None:
                if not keep_undated:
                    continue
            elif epoch < cutoff:
                continue
            seen_links.add(link)
            out.append(item)
    # Newest first (undated sink to the bottom).
    out.sort(key=lambda x: x["epoch"] or 0, reverse=True)
    return out
