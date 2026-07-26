# DiscordPush — personal alerts on GitHub Actions

A serverless personal alerting system. No hosting, no database — everything runs
on GitHub Actions cron, and state is persisted by committing small JSON files
back to the repo. Two independent systems:

1. **Pokémon card price monitor** — polls eBay Australia for cards on a watchlist
   and pings Discord when a listing drops to/below your target price. Every
   candidate is vetted by **Claude Haiku** first, so you only get pinged on
   listings that look like a genuine deal for the actual card (not proxies,
   lots, fakes, or scams). Alerts carry **historical context**: the system keeps
   its own daily-low price history per card (committed to `state/price_history.json`),
   so a ping can say *"🔻 lowest since tracking began"* or *"cheapest in 90 days"* —
   and, if you add an optional **PriceCharting** token, *"38% under market value"*.
2. **News briefs & alerts** — a **daily 7am (Sydney) morning digest** for cyber
   security, general tech/IT, and AI, each posted to its own Discord channel;
   plus an **hourly scan** for major Australian cyber incidents that fires an
   urgent push the moment something significant lands.

Everything is Python, scheduled by cron, with per-stream Discord webhooks.

---

## How it works

| Workflow | Schedule (UTC) | What it does |
|---|---|---|
| `.github/workflows/pokemon-monitor.yml` | every 30 min | searches eBay AU, verifies with Haiku, alerts on deals |
| `.github/workflows/news-digest.yml` | `20:00` & `21:00` daily | one of the two fires at 7am Sydney (DST-aware in code) and posts the three digests |
| `.github/workflows/urgent-cyber.yml` | hourly | scans AU cyber feeds, confirms with Haiku, pushes urgent alerts |

State lives in `state/` and is committed back after each run (`pokemon_seen.json`,
`news_seen.json`, `price_history.json`) so alerts are de-duplicated across runs —
and the price history accumulates into a real time series — without any database.

**On historical prices:** true "cheapest since 2022" can't come from an API
(PriceCharting's API returns *current* market values, not a full daily series),
so the system builds its own history from the day you start it. PriceCharting is
an optional add-on that supplies present-day market value for "% under market"
context; the "cheapest since \<tracking start>" signal needs no external service
and grows more useful the longer it runs.

```
config/watchlist.json   # cards + target prices (edit me)
config/feeds.yaml        # RSS sources per category (edit me)
src/common/              # config, Discord, Claude, state, fx helpers
src/pokemon/             # eBay client, PriceCharting, price history, monitor
src/news/                # RSS feeds + digest + urgent entry points
```

---

## Setup

👉 **Follow the step-by-step runbook: [SETUP.md](SETUP.md).** It walks you
through pushing to GitHub, collecting the keys, adding secrets, and testing —
with a checkpoint after every step.

At a glance, you'll need:

| Thing to collect | Where | Secret name(s) |
|---|---|---|
| Anthropic API key | <https://console.anthropic.com/> | `ANTHROPIC_API_KEY` |
| eBay App ID + Cert ID | <https://developer.ebay.com/> | `EBAY_APP_ID`, `EBAY_CERT_ID` |
| Discord webhook URLs | Discord channel → Integrations → Webhooks | `DISCORD_WEBHOOK_CARDS`, `DISCORD_WEBHOOK_CYBER`, `DISCORD_WEBHOOK_TECH`, `DISCORD_WEBHOOK_AI`, `DISCORD_WEBHOOK_URGENT` |

Then customise:

- **Cards:** edit `config/watchlist.json` — set `query`, `target_aud`, and
  `exclude` keywords per card. The example targets are placeholders; tune them.
- **Feeds:** edit `config/feeds.yaml`. Broken/unreachable feeds are skipped
  automatically, so a dead URL won't break a run — but verify the ones that
  matter to you (feed URLs move over time).

Optional secrets:

- `PRICECHARTING_TOKEN` — a [PriceCharting API](https://www.pricecharting.com/api-documentation)
  token (paid plan). When set, card alerts show current market value and "% under
  market". Leave it unset to skip that context; the daily-low history still works.
- `EBAY_MARKETPLACE_ID` — defaults to `EBAY_AU`.

---

## Trying it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# export the same secrets as env vars, then:
python -m src.pokemon.monitor          # run the card monitor once
python -m src.news.urgent              # run the urgent scan once
python -m src.news.digest --force      # send the digests now (ignore 7am gate)
```

You can also trigger any workflow manually from the **Actions** tab
(**Run workflow**). The digest workflow’s manual run defaults to `force = true`
so you get output immediately rather than waiting for 7am Sydney.

---

## Notes & tuning

- **GitHub cron is best-effort**, not exact — runs can be delayed several
  minutes under load. Fine for these use cases; the urgent scan overlaps its
  window (90 min) so nothing slips through a scheduling gap.
- **Cost control:** the card verifier only calls Claude for listings already at
  or below your target; the urgent scanner keyword-pre-filters before calling
  Claude. Both use Haiku.
- **De-duplication:** a card listing is re-alerted only if its total price drops
  by ≥ $5 since last seen; urgent articles are keyed by link and remembered for
  14 days. State is pruned so the repo stays small.
- **Digest timing** is gated in Python against `Australia/Sydney` 07:00, so
  daylight saving is handled without editing the cron.
- The urgent alert posts `@here`. Remove that in `src/news/urgent.py` if you
  don't want the mention.

---

## Prerequisites summary

- A GitHub repo with Actions enabled and read/write workflow permissions.
- Five Discord webhook URLs (or fewer — a missing webhook just skips that stream).
- An eBay developer app (App ID + Cert ID).
- An Anthropic API key.
