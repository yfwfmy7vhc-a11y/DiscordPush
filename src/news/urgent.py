"""Hourly urgent AU-cyber scanner — entry point.

Flow:
  1. Pull the last ~90 min of items from the urgent feed list.
  2. Cheap keyword pre-filter (AU + cyber signals) to avoid spending model calls
     on obviously-irrelevant items.
  3. Ask Claude Haiku to confirm each candidate is a MAJOR, time-sensitive AU
     cyber incident.
  4. Dedupe against state and post confirmed alerts to the urgent Discord channel.

Run:  python -m src.news.urgent
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from ..common import claude_client, config, discord, state
from . import feeds

# Overlap the hourly cron a little so nothing slips through a scheduling gap.
_WINDOW_SECONDS = 90 * 60
_STATE_TTL_DAYS = 14
_MAX_CANDIDATES = 25  # safety cap on model calls per run

_AU_TERMS = (
    "australia", "australian", "aussie", "acsc", "asd", "oaic", "nsw", "victoria",
    "queensland", "canberra", "sydney", "melbourne", "brisbane", "perth", ".au",
    "telstra", "optus", "medibank", "commonwealth", "centrelink", "ato",
)
_CYBER_TERMS = (
    "breach", "hack", "ransomware", "malware", "exploit", "vulnerability", "cve",
    "attack", "cyber", "data leak", "leaked", "compromise", "zero-day", "zero day",
    "phishing", "ddos", "outage", "advisory", "exposed", "stolen", "extortion",
)

_SEVERITY_EMOJI = {"low": "🟡", "medium": "🟠", "high": "🔴", "critical": "🚨"}


def _prefilter(item: dict[str, Any]) -> bool:
    text = f"{item.get('title', '')} {item.get('summary', '')} {item.get('link', '')}".lower()
    has_cyber = any(t in text for t in _CYBER_TERMS)
    has_au = any(t in text for t in _AU_TERMS)
    # cyber.gov.au / itnews AU feeds are AU by construction — let cyber-only pass
    # from AU-domiciled sources, but require both signals for global sources.
    source = (item.get("source") or "").lower()
    link = (item.get("link") or "").lower()
    au_source = "cyber.gov.au" in link or "itnews.com.au" in link or "cyberdaily" in link \
        or "australia" in source or ".au" in link
    return has_cyber and (has_au or au_source)


def _key(item: dict[str, Any]) -> str:
    return hashlib.sha256(item["link"].encode("utf-8")).hexdigest()[:16]


def _alert_embed(item: dict[str, Any], verdict: dict[str, Any]) -> dict[str, Any]:
    sev = verdict.get("severity", "medium")
    emoji = _SEVERITY_EMOJI.get(sev, "🟠")
    headline = verdict.get("headline") or item.get("title", "")
    return discord.make_embed(
        title=f"{emoji} {headline}"[:256],
        description=f"{verdict.get('why', '')}\n\n_{item.get('title', '')}_",
        url=item.get("link") or None,
        color=discord.COLORS["urgent"],
        fields=[
            {"name": "Severity", "value": sev.upper(), "inline": True},
            {"name": "Source", "value": str(item.get("source", "?")), "inline": True},
        ],
        footer="Urgent AU cyber alert",
    )


def run() -> int:
    urls = config.load_feeds().get("urgent", [])
    seen = state.load(config.NEWS_STATE_PATH)

    items = feeds.fetch_recent(urls, _WINDOW_SECONDS)
    candidates = [it for it in items if _key(it) not in seen and _prefilter(it)]
    print(f"{len(items)} recent, {len(candidates)} candidate(s) after pre-filter")

    embeds: list[dict[str, Any]] = []
    for item in candidates[:_MAX_CANDIDATES]:
        key = _key(item)
        verdict = claude_client.classify_urgent(item)
        seen[key] = {"ts": time.time(), "title": item.get("title", "")[:200]}
        if verdict.get("is_urgent_au_cyber"):
            print(f"  [URGENT/{verdict.get('severity')}] {item.get('title', '')[:70]}")
            embeds.append(_alert_embed(item, verdict))
        else:
            print(f"  [skip] {item.get('title', '')[:70]}")

    if embeds:
        discord.send_embeds(
            config.webhook("urgent"),
            embeds,
            content="@here Major AU cyber incident detected" if len(embeds) else "",
        )

    seen = state.prune_older_than(seen, _STATE_TTL_DAYS)
    state.save(config.NEWS_STATE_PATH, seen)
    print(f"Done. {len(embeds)} urgent alert(s) sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
