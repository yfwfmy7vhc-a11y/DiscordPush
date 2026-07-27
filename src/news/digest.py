"""Daily morning digests — entry point.

Gathers the last ~24h of headlines for each category (cyber, tech, ai),
summarises them with Claude Haiku, and posts one embed to each category's
Discord channel.

The GitHub Actions cron runs this several times each morning (UTC). Instead of
requiring the clock to read *exactly* 7am — which a late GitHub run would miss —
we send once when the Sydney time is anywhere in the morning window AND we haven't
already sent today. A tiny state file (digest_state.json) records the last send
date, so whichever morning run fires first delivers it and the rest are no-ops.
This survives daylight saving and GitHub's habit of running crons late.

Run:  python -m src.news.digest          (respects the morning-window + once-a-day gate)
      python -m src.news.digest --force   (send now, ignore the gate; doesn't consume the day)
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..common import claude_client, config, discord, state
from . import feeds

_WINDOW_SECONDS = 26 * 3600  # a little over 24h for slack
_MAX_ITEMS_PER_CATEGORY = 45  # cap what we hand the model
_MIN_ITEMS = 10  # if fewer than this land in the window, fall back to newest-N
# Auto-send only when Sydney time is in [DIGEST_HOUR_LOCAL, _MORNING_END_HOUR),
# i.e. 07:00–11:59 — wide enough to absorb a late cron, narrow enough that a
# stray run at night never fires.
_MORNING_END_HOUR = 12


def _today_local() -> str:
    return datetime.now(ZoneInfo(config.LOCAL_TZ)).date().isoformat()


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
    now_local = datetime.now(ZoneInfo(config.LOCAL_TZ))
    today = _today_local()
    dstate = state.load(config.DIGEST_STATE_PATH)

    if not force:
        if not (config.DIGEST_HOUR_LOCAL <= now_local.hour < _MORNING_END_HOUR):
            print(f"[skip] {now_local:%H:%M %Z} outside the "
                  f"{config.DIGEST_HOUR_LOCAL:02d}:00–{_MORNING_END_HOUR:02d}:00 window.")
            return 0
        if dstate.get("last_sent") == today:
            print(f"[skip] digest already sent today ({today}).")
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

    # Record the send so later morning crons today become no-ops. A manual
    # --force run deliberately doesn't consume the day, so it won't block the
    # real scheduled digest.
    if not force:
        dstate["last_sent"] = today
        state.save(config.DIGEST_STATE_PATH, dstate)
        print(f"marked digest sent for {today}")

    return 0


if __name__ == "__main__":
    raise SystemExit(run(force="--force" in sys.argv))
