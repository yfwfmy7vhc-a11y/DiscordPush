"""Daily morning digests — entry point.

Gathers the last ~24h of headlines for each category (cyber, tech, ai),
summarises them with Claude Haiku, and posts one embed to each category's
Discord channel.

The GitHub Actions cron runs this at a couple of UTC times bracketing 7am
Sydney; we gate on local time here so exactly one run per day actually sends
(handles daylight saving without touching the workflow).

Run:  python -m src.news.digest          (respects the 7am-Sydney gate)
      python -m src.news.digest --force   (send now, ignore the time gate)
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..common import claude_client, config, discord
from . import feeds

_WINDOW_SECONDS = 26 * 3600  # a little over 24h for slack
_MAX_ITEMS_PER_CATEGORY = 45  # cap what we hand the model
_MIN_ITEMS = 10  # if fewer than this land in the window, fall back to newest-N


def _should_run_now() -> bool:
    now_local = datetime.now(ZoneInfo(config.LOCAL_TZ))
    return now_local.hour == config.DIGEST_HOUR_LOCAL


def _digest_embed(category: str, brief: str, count: int) -> dict[str, Any]:
    titles = {
        "cyber": "🛡️ Cyber Security — Morning Brief",
        "tech": "💻 Tech & IT — Morning Brief",
        "ai": "🤖 AI — Morning Brief",
    }
    date_str = datetime.now(ZoneInfo(config.LOCAL_TZ)).strftime("%A %d %B %Y")
    return discord.make_embed(
        title=titles.get(category, f"{category} — Morning Brief"),
        description=brief or "_No notable items in the last 24h._",
        color=discord.COLORS.get(category, 0x95A5A6),
        footer=f"{date_str} • {count} stories scanned • Australia/Sydney",
    )


def run(force: bool = False) -> int:
    if not force and not _should_run_now():
        now_local = datetime.now(ZoneInfo(config.LOCAL_TZ))
        print(f"[skip] local time {now_local:%H:%M %Z} != {config.DIGEST_HOUR_LOCAL}:00; not sending.")
        return 0

    feeds_cfg = config.load_feeds().get("digests", {})
    for category, urls in feeds_cfg.items():
        print(f"\n== digest: {category} ({len(urls)} feeds)")
        items = feeds.fetch_recent(
            urls, _WINDOW_SECONDS, min_items=_MIN_ITEMS, max_items=_MAX_ITEMS_PER_CATEGORY
        )
        print(f"  {len(items)} recent items")
        if not items:
            brief = ""
        else:
            try:
                brief = claude_client.summarize_digest(category, items)
            except Exception as exc:
                print(f"  [warn] summarise failed: {exc}")
                continue

        embed = _digest_embed(category, brief, len(items))
        discord.send_embeds(config.webhook(category), [embed])
        print(f"  posted {category} digest")

    return 0


if __name__ == "__main__":
    raise SystemExit(run(force="--force" in sys.argv))
